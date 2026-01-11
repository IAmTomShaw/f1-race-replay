# Contributing Guidelines

Thank you for your interest in contributing to our project. Whether it's a bug report, new feature, correction, or additional documentation, we greatly value feedback and contributions from our community.

Please read through this document before submitting any issues or pull requests to ensure we have all the necessary information to effectively respond to your bug report or contribution.

To read about setting up your development environment, please refer to the [development-setup.md](docs/contributing/development-setup.md) file.

## Table of Contents
- [Contributing Guidelines](#contributing-guidelines)
  - [Table of Contents](#table-of-contents)
  - [Reporting Bugs/Feature Requests](#reporting-bugsfeature-requests)
  - [Contributing via Pull Requests](#contributing-via-pull-requests)
  - [Commit Message Format](#commit-message-format)
    - [Examples:](#examples)
  - [Coding Style](#coding-style)
    - [Typescript](#typescript)
    - [Python](#python)


## Reporting Bugs/Feature Requests

We welcome you to use the GitHub issue tracker to report bugs or suggest features.

When filing an issue, please check existing open, or recently closed, issues to make sure somebody else hasn't already reported the issue. Please try to include as much information as you can. Details like these are incredibly useful:

- A reproducible test case or series of steps
- The version of our code being used
- Any modifications you've made relevant to the bug
- Anything unusual about your environment or deployment

## Contributing via Pull Requests

Contributions via pull requests are much appreciated. Before sending us a pull request, please ensure that:

1. You are working against the latest source on the _main_ branch.
2. You check existing open, and recently merged, pull requests to make sure someone else hasn't addressed the problem already.
3. You open an issue to discuss any significant work - we would hate for your time to be wasted.

To send us a pull request, please:

1. Fork the repository.
2. Modify the source; please focus on the specific change you are contributing. If you also reformat all the code, it will be hard for us to focus on your change.
3. Commit to your fork using clear commit messages.
4. Send us a pull request, answering any default questions in the pull request interface.

## Commit Message Format

Commit messages should be clear and descriptive. A recommended format is:

```
<type>: <short summary>
```

### Examples:

- `fix: resolve null pointer exception in parser`
- `feat: add user authentication support`
- `docs: add documentation for the project`

## Coding Style

### Typescript

We use [Prettier](https://prettier.io/) to format the code. You can run the following command to format the code.

```bash
npm run format
```

Or install the [Prettier VS Code extension](https://marketplace.visualstudio.com/items?itemName=esbenp.prettier-vscode) to format the code automatically.

### Python

TBC
