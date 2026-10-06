# Security and privacy

Do not commit a real Personal OS vault, managed sources, indexes, caches, logs, conflict artifacts, or conversation exports. Index and embedding files may contain recoverable sensitive text even when Markdown is absent.

Use the synthetic demo vault for issues and pull requests. Never upload real Source Evidence, screenshots with personal information, or a private Golden Set.

For a suspected secret or privacy exposure, do not open a public issue containing the data. Contact the repository owner through GitHub's private security reporting feature once enabled. Until then, provide only a synthetic description and request a private channel.

Run `python scripts/privacy_scan.py` before every publication.

## Publisher-private scanning

The public scanner contains only generic secret, identifier, and absolute-path rules. Maintainers can add local literals or regular expressions with `--private-patterns <path>` or the `PERSONAL_OS_PRIVATE_PATTERNS` environment variable. The JSON file accepts a list, or an object with a `patterns` list; entries may be strings, `{ "literal": "..." }`, or `{ "regex": "..." }`.

Keep that file outside the repository. Private pattern filenames are ignored by Git and rejected by the public-artifact gate if copied into the public tree. Scan reports record only the rule category, relative file, and line number; they never echo the matched private text.
