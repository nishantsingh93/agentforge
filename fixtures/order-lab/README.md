# Owned order fixture

The service owns normalization and validation. The API delegates to it.
Null status becomes pending; unsupported statuses raise ValueError.
All data is synthetic. No auth implementation or external database exists here.
