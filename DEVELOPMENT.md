# Development

Install Python dependencies:

```
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

## Pre-commit hooks

Install and activate the pre-commit hooks during development:

```
pre-commit install
# (Optional) run on all files first, just to check
pre-commit run --all-files
```

Afterwards, whenever a local commit is made, the hooks will be run.
Hooks include style checkers and pyright.


## Adding a dependency

Dependency with version should be specified in in `requirements.txt`.

After than, you should add the same dependency in `.pre-commit-config.yaml`, in the `additional_dependencies:` field of the pyright hook.
This tells pyright to install the corresponding dependencies when running as
a pre-commit hook.
If not added, pyright may report import error during pre-commit.
