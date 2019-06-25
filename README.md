# CrateD
#### Made with Python, SQLite, and peewee-ORM

Don't let the flashy UI fool you. CrateD has some serious Python techniques under the covers. In the demo below, we dynamically create Peewee Models which create tables in a SQLite database. As the user builds the data model, the system records metadata about the models and their fields. This metadata is stored in a special table so that the models can be reconstructed on the fly when the system restarts.
[Try it!](https://crated-demo.patrickshouse.repl.run)

![demo](https://media.giphy.com/media/kaaHywHB1g5y4A2JHO/giphy.gif)

