# DB-IP City Lite (October 2026)

Source: https://db-ip.com/db/download/ip-to-city-lite

Database copyright DB-IP.com, distributed under the Creative Commons Attribution
4.0 International license: https://creativecommons.org/licenses/by/4.0/

Attribution: [IP Geolocation by DB-IP](https://db-ip.com).
The audit-log page includes this attribution wherever results are displayed.

The original, unchanged compressed MMDB is committed alongside its SHA-256 and
size in `metadata.json`. It is copied into the image by the existing Dockerfile.
No download occurs during builds, startup, login, or lookup. The Python reader
decompresses it once into process memory and then closes the file.

To update deliberately, download a new monthly release from the official source,
verify and record its checksum and sample lookups, update the filename in
`app/core/ip_location.py`, and rebuild. Never replace it automatically at startup.

This free edition has reduced coverage and accuracy; regions/cities describe IP
allocation and cannot establish a visitor's physical location. It may return
English names; a small display-only Chinese translation map does not change any
IP ranges or invent missing location information.
