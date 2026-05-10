# Agent Notes

## GitHub Access

- Use SSH for GitHub verification, fetches, and pushes.
- The working remote should be `git@github.com:QM-Code/kmqdb-ttrpg.git`.
- Do not rely on the HTTPS remote for verification or pushing from agent
  environments; it can fail with an interactive credential prompt such as
  `could not read Username for 'https://github.com': Device not configured`.
- A quick SSH verification command is:

```sh
ssh -T git@github.com
```

GitHub returns a success message and exits nonzero because it does not provide
shell access; treat the authenticated greeting as a successful verification.
