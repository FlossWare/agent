# Command-policy threat model

`CommandPolicy` is a security boundary, not a convenience filter. Treat every command and argument produced by a worker model as untrusted input.

## Default capabilities

| Capability | Default | Security invariant |
|---|---|---|
| Shell execution | Off | Worker cannot turn an argv request into a shell script |
| Network | Off | Network-capable commands and remote Git actions are rejected |
| Filesystem | Workspace only | Paths cannot resolve outside the assigned workspace |
| Git hooks | Off | Worker cannot install executable hooks in the workspace Git metadata |
| Nested command execution | Off | `find -exec`, `-execdir`, `-ok`, `-okdir`, and equivalent command-spawning features are rejected |
| Privilege escalation | Off | `sudo`, `su`, `doas`, and equivalent commands are rejected |

## High-risk command families

The policy must reject these even when the executable itself is allowlisted:

- `find` command-execution actions (`-exec`, `-execdir`, `-ok`, `-okdir`)
- Git actions that execute shell commands, including submodule `foreach`, rebase/am/filter-branch execution flags, and equivalent forms
- Git network actions when `allow_network=False`, including `clone`, `fetch`, `pull`, `push`, `ls-remote`, and network-capable submodule/remote actions
- executable paths or path-taking options that escape the workspace
- shell metacharacters when `allow_shell=False`
- absolute paths, traversal paths, and symlink escapes
- writes into `.git` metadata, including hooks

## Testing requirements

Every policy rule should have both positive and negative tests. In particular, regression tests should cover:

1. long and short options
2. concatenated short options such as `-C/path`
3. `--option=value` forms
4. symlink and nested-symlink paths
5. Git global options before the subcommand
6. shell-producing Git flags
7. `find` execution variants
8. remote URLs and SCP-style Git remotes
9. shell metacharacters and command substitution
10. malformed or model-generated argv containing unexpected types

A command that is not explicitly safe should fail closed. The worker model must never be the component that decides whether a command is safe.
