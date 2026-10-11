# T3 Code Customizations

Unofficial Linux customizations for T3 Code Nightly. This repository holds changes applied to the installed app without compiling T3 or maintaining a full source fork, and can grow to include more UI and workflow changes.

## Persisted thread list

The first customization adds a **Persisted** thread list to T3 Code's sidebar.

- Right-click a thread and choose **Move to Persisted**.
- Persisted sits at the top, beneath the sidebar search.
- Expanded members use T3's full native thread cards.
- Drag a Persisted card just like a normal T3 thread to set its order. It uses the native drag sensor, card preview, collision detection, and row animations.
- New members go to the bottom. Existing members initially follow the order they were added. Activity does not change this order.
- A divider marks the end of the expanded list.
- Collapse and expansion reuse T3's native shelf animations and reduced-motion handling.
- Right-click a member and choose **Remove from Persisted** to restore its normal group.
- Membership, manual order, and collapse state are saved separately from T3's thread database.

Moving a thread to Persisted does not settle, snooze, archive, move projects, or alter its conversation history. Existing threads work too. Project filters and search still apply. Archived and deleted threads remain governed by T3's normal lifecycle.

## Requirements

- Linux with Python 3, `cp`, and a working T3 Code Nightly installation.
- The installer currently targets the `t3code-nightly-bin` package at `/opt/t3code-nightly-bin`, its `/usr/bin/t3code-nightly` launcher, and its desktop entries.
- T3's current sidebar. The optional legacy sidebar is not customized.
- Node.js is needed only for the JavaScript unit tests. The launcher uses the installed Electron runtime to check transformed JavaScript.

Tested on `0.0.46-nightly.20261011.2980`. This modifies internal integration points, so later nightlies may require an adapter update. Other operating systems and installation layouts have not been tested.

## Install

```sh
git clone https://github.com/vytorrennan/t3code-customizations.git
cd t3code-customizations
python3 install.py
```

The installer copies the customization into `~/.local/share/t3code-persisted`, creates user launchers, and backs up existing user desktop entries before updating them. It preserves existing Persisted membership and backups when run again.

The installed directory keeps its original name so existing launchers and saved membership continue to work after the repository rename.

Quit and reopen T3 Code once to activate it. Launching the customization while an old T3 instance is running only forwards to that existing instance.

## Nightly updates

Continue updating the official nightly through your usual package manager. At launch, the customization checks the installed package and generates a fresh patched copy when needed. It does not modify `/opt` or replace the package manager's installation.

Every expected integration point is checked, and transformed JavaScript is syntax-checked before launch. An unsupported build launches the untouched official app and retains the saved membership. If membership storage or the customization bridge is unavailable, threads appear in their native groups.

Saved list data can survive updates; compatibility of the customization with every future nightly is not guaranteed.

To update the customization itself:

```sh
git pull --ff-only
python3 install.py
```

Then quit and reopen T3 Code.

## Local files

| Purpose | Location |
| --- | --- |
| Custom launcher | `~/.local/bin/t3code-nightly` |
| Official-app bypass | `~/.local/bin/t3code-official-nightly` |
| Installed source | `~/.local/share/t3code-persisted/src/` |
| Membership, manual order, and collapse state | `~/.local/share/t3code-persisted/data/membership.json` |
| Previous membership document | The adjacent `membership.json.bak` |
| Original user desktop entries | `~/.local/share/t3code-persisted/backups/` |
| Generated app copies | `~/.cache/t3code-persisted/builds/` |

Membership records contain only environment IDs, thread IDs, and dates. Their array order is the saved list order. Reordering preserves members hidden by search and project filters. The file is written atomically before thread visibility changes. If it becomes unreadable, the customization leaves it untouched and uses native grouping. Two recent generated app copies are retained, along with any copy still running.

## Bypass or uninstall

To use the official app temporarily, quit T3 and run:

```sh
~/.local/bin/t3code-official-nightly
```

To restore the previous desktop entries and remove the custom launcher:

```sh
python3 ~/.local/share/t3code-persisted/uninstall.py
```

Source and membership remain on disk for recovery. The official installation is unchanged.

## Tests

Run the storage and renderer tests:

```sh
node --test tests/storage.test.cjs tests/renderer.test.cjs
```

With the supported nightly installed, check the adapter:

```sh
python3 tests/adapter_test.py
```

With a graphical Linux session and an initialized local T3 database, exercise the actual Electron UI:

```sh
python3 tests/native.py
```

The native test uses isolated app directories and synthetic threads. It copies only database schema and migration bookkeeping from the local T3 database, never personal threads, messages, credentials, or provider sessions. It checks native menus, full cards, top placement, collapse animations, native card dragging and preview, cancellation, saved order after a restart into a fresh app copy, removal, and corrupt-storage fallback. Its fixtures, logs, and screenshot stay under `/tmp/t3-persisted-native-test/`.

## Repository contents

This repository contains customization source, an installer, an uninstaller, and tests with synthetic thread data. It contains no personal thread data, membership files, credentials, desktop backups, logs, screenshots, generated application copies, or bundled T3 application code. The ignore rules exclude local data and generated artifacts from future commits.
