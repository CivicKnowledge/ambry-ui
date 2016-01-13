ambry-admin
===========

Ambry user interface and management CLI module


Running the UI
--------------

To run the UI in local, development mode:

    ambry ui start

To run locally with gunicorn:

    $ run-ambryui-gunicorn

Or, for more complex configurations, call gunicorn directly:

    $ gunicorn -w 4 --max-requests 10 -b 0.0.0.0:8080 ambry_ui:app


CLI
---

Install the CLI into Ambry with:

    ambry config installcli ambry_ui

Run ``ambry ui -h`` to check that it worked.

The main commands are:

- start: Run a UI locally in development mode
- user:
    - user add: Add or edit a user
    - user admin: Add or remove admin priveledges
    - user remove: Remove a user
    - user list: List all users.

