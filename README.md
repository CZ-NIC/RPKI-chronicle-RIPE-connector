# RIPE NCC Validator connector

## Introduction
This module provides a data source that takes results from either local or remote RIPE NCC
RPKI Validator [1] over REST API [2]. Supported protocols are HTTP and HTTPS. HTTPS is
strongly recommended for connections to a remote validator.

## Deployment
For testing purposes we recommend using openly available instance of RIPE NCC RPKI Validator
accessible on a public URL [3].

The data obtained from the RIPE NCC RPKI are saved in an aggregated and space-saving way
to DB for the frontend to display them and perhaps other applications can (read-only) access
them. DB schema is part of the front-end.

The DB connection URL is needed in a file `dbconn.py` in variable `SQLALCHEMY_DATABASE_URI`.
Example:

```
SQLALCHEMY_DATABASE_URI = 'postgresql+psycopg2://username:password@host/db_name'
```

Utilities for testing and long-term reliable operation are provided to help detect problems
that might damage the dataset.

The preferred way of operation for the connector is to run from cron as a dedicated user:

```
0  *	* * *	rpkichronicle	/path/to/rpkival_save_records.py >>/path/to/connector.log 2>&1

```

The STDOUT from the script is empty unless an error occures. STDERR is used for logging
of the script progress. It may / should be redirected to a log file. Following logrotate
script for the log file is recommended:

```
/path/to/rpkichronicle/*.log {
	weekly
	missingok
	rotate 8
	compress
	delaycompress
	notifempty
	create 0640 rpkichronicle rpkichronicle
}
```

* [1] https://www.ripe.net/manage-ips-and-asns/resource-management/certification/tools-and-resources
* [2] https://www.ripe.net/support/documentation/developer-documentation/rpki-validator-api/rpki-validator-api
* [3] https://rpki-validator.ripe.net/
