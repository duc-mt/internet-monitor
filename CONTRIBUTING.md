# Contributing Guidelines

Thank you for investing your time in contributing to our project!

## Branching Strategy (GitHub Flow)

We follow the **GitHub Flow** for development. Please avoid committing directly to the `master` branch.

1. **Create a feature branch:**
   Branch off from `master` to create your feature or bugfix branch. Use a descriptive name:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-description
   ```

2. **Commit your changes:**
   We follow [Conventional Commits](https://www.conventionalcommits.org/). Please prefix your commits with the appropriate type:
   - `feat:` A new feature
   - `fix:` A bug fix
   - `docs:` Documentation only changes
   - `style:` Changes that do not affect the meaning of the code
   - `refactor:` A code change that neither fixes a bug nor adds a feature
   - `perf:` A code change that improves performance
   - `test:` Adding missing tests or correcting existing tests
   - `chore:` Changes to the build process or auxiliary tools

3. **Open a Pull Request:**
   Once your branch is ready, push it to GitHub and open a Pull Request (PR) against the `master` branch. The PR template will guide you through the review process.

## Pre-commit Hooks

We use `pre-commit` to ensure code quality before pushing. 

To set it up locally:
1. Install pre-commit: `pip install pre-commit`
2. Install the git hook scripts: `pre-commit install`

Now `pre-commit` will run automatically on `git commit` to check for trailing whitespaces, correct formatting, and linting errors.
