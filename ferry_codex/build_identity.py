"""Build identity embedded in source and replaced in release artifacts."""

PUBLIC_VERSION = "0.1.1"
# A release build replaces this with the exact clean source commit.  Keeping the
# source marker explicit prevents an unpacked checkout from masquerading as an
# immutable distribution.
SOURCE_COMMIT = "unbuilt"
FULL_VERSION = f"{PUBLIC_VERSION}+{SOURCE_COMMIT[:12]}"
