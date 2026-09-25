from __future__ import annotations

import sys
from datetime import datetime, timezone

import aiosqlite

from app.database.connection import write_transaction
from app.models.target import TargetCreate, TargetOut, TargetUpdate
from app.monitoring import network_info


def _row_to_target(row: aiosqlite.Row) -> TargetOut:
    return TargetOut(
        id=row["id"],
        name=row["name"],
        host=row["host"],
        protocol=row["protocol"],
        port=row["port"],
        is_gateway=bool(row["is_gateway"]),
        enabled=bool(row["enabled"]),
        interval_seconds=row["interval_seconds"],
        created_at=row["created_at"],
    )


async def list_targets(conn: aiosqlite.Connection, *, enabled_only: bool = False) -> list[TargetOut]:
    query = "SELECT * FROM targets"
    if enabled_only:
        query += " WHERE enabled = 1"
    query += " ORDER BY is_gateway DESC, id ASC"
    async with conn.execute(query) as cursor:
        rows = await cursor.fetchall()
    return [_row_to_target(r) for r in rows]


async def get_target(conn: aiosqlite.Connection, target_id: int) -> TargetOut | None:
    async with conn.execute("SELECT * FROM targets WHERE id = ?", (target_id,)) as cursor:
        row = await cursor.fetchone()
    return _row_to_target(row) if row else None


async def create_target(conn: aiosqlite.Connection, data: TargetCreate) -> TargetOut:
    created_at = datetime.now(timezone.utc).isoformat()
    async with write_transaction() as tx:
        cursor = await tx.execute(
            """
            INSERT INTO targets (name, host, protocol, port, is_gateway, enabled, interval_seconds, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.name,
                data.host,
                data.protocol,
                data.port,
                int(data.is_gateway),
                int(data.enabled),
                data.interval_seconds,
                created_at,
            ),
        )
        target_id = cursor.lastrowid
    if target_id is None:
        raise RuntimeError("Failed to insert target")
    target = await get_target(conn, target_id)
    if target is None:
        raise RuntimeError("Failed to retrieve created target")
    return target


async def update_target(conn: aiosqlite.Connection, target_id: int, data: TargetUpdate) -> TargetOut | None:
    existing = await get_target(conn, target_id)
    if existing is None:
        return None
    fields = data.model_dump(exclude_unset=True)
    if not fields:
        return existing
    set_clause = ", ".join(f"{key} = ?" for key in fields)
    values = [(int(v) if isinstance(v, bool) else v) for v in fields.values()]
    async with write_transaction() as tx:
        await tx.execute(
            f"UPDATE targets SET {set_clause} WHERE id = ?",
            (*values, target_id),
        )
    return await get_target(conn, target_id)


async def delete_target(conn: aiosqlite.Connection, target_id: int) -> bool:
    async with write_transaction() as tx:
        cursor = await tx.execute("DELETE FROM targets WHERE id = ?", (target_id,))
    return cursor.rowcount > 0


async def seed_default_targets(conn: aiosqlite.Connection) -> None:
    """Populate defaults on first run, and update Gateway/WAN IPs on every startup."""
    existing = await list_targets(conn)
    wan_ip = await network_info.get_wan_ip() or "127.0.0.1"
    gateway_ip = await _detect_gateway()

    if existing:
        # Update existing Gateway and WAN targets to current IPs dynamically
        gateway_target = next((t for t in existing if t.name == "Gateway"), None)
        wan_target = next((t for t in existing if t.name == "WAN"), None)
        
        async with write_transaction() as tx:
            if gateway_target and gateway_target.host != gateway_ip:
                await tx.execute("UPDATE targets SET host = ? WHERE id = ?", (gateway_ip, gateway_target.id))
            if wan_target and wan_target.host != wan_ip:
                await tx.execute("UPDATE targets SET host = ? WHERE id = ?", (wan_ip, wan_target.id))
                
        # Check if WAN target is missing and add it for backward compatibility
        if not wan_target:
            await create_target(conn, TargetCreate(name="WAN", host=wan_ip, protocol="icmp", interval_seconds=5))
        return

    defaults = [
        TargetCreate(
            name="Gateway", host=gateway_ip, protocol="icmp", is_gateway=True, interval_seconds=5
        ),
        TargetCreate(name="WAN", host=wan_ip, protocol="icmp", interval_seconds=5),
        TargetCreate(name="Google DNS", host="8.8.8.8", protocol="icmp", interval_seconds=5),
        TargetCreate(name="Cloudflare DNS", host="1.1.1.1", protocol="icmp", interval_seconds=5),
    ]
    for target in defaults:
        await create_target(conn, target)


async def _detect_gateway() -> str:
    """
    Best-effort default-gateway detection, falling back to a common LAN IP
    if nothing could be determined at all. Linux reads /proc/net/route
    directly (no subprocess needed); macOS has no /proc filesystem, so it
    shells out to `route -n get default` instead (see
    app.monitoring.network_info.get_default_gateway_macos); Windows has
    neither, so it shells out to `route print -4` instead (see
    get_default_gateway_windows) - three genuinely different mechanisms,
    not a shared code path.
    """
    if sys.platform == "darwin":
        try:
            gateway = await network_info.get_default_gateway_macos()
            if gateway:
                return gateway
        except Exception:  # pragma: no cover - defensive: seeding must never crash on this
            pass
        return "192.168.1.1"

    if sys.platform == "win32":
        try:
            gateway = await network_info.get_default_gateway_windows()
            if gateway:
                return gateway
        except Exception:  # pragma: no cover - defensive: seeding must never crash on this
            pass
        return "192.168.1.1"

    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                fields = line.strip().split()
                if len(fields) >= 3 and fields[1] == "00000000":
                    hex_ip = fields[2]
                    octets = [str(int(hex_ip[i : i + 2], 16)) for i in (6, 4, 2, 0)]
                    return ".".join(octets)
    except (OSError, ValueError, IndexError):
        pass
    return "192.168.1.1"
