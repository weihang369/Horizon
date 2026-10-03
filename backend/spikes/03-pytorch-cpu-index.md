# Spike (c): CPU torch from the `pytorch-cpu` index

**Question.** Does `uv` resolve `torch` + `torchvision` from `https://download.pytorch.org/whl/cpu` (`explicit = true`, marker `sys_platform != 'darwin'`) inside the optional `docling` group?

**Result: yes.** `uv lock` (run by `uv sync`) resolved, with nothing from the group installed:

| Package | Non-macOS | macOS |
|---|---|---|
| torch | 2.14.1+cpu (pytorch-cpu index) | 2.14.1 (PyPI) |
| torchvision | 0.29.1+cpu (pytorch-cpu index) | 0.29.1 (PyPI) |
| docling | 2.133.0 (PyPI) | 2.133.0 (PyPI) |

- `uv.lock` grows to about 244 KB.
- The core `uv sync` doesn't install the group (only `dev` is a default group).
- `npm run setup:docling` (`uv sync --group docling`) installs it. Model download (`horizon models fetch`) arrives in M5.
