from peewee import Model, SqliteDatabase, TextField, DateTimeField, SQL, ForeignKeyField, IntegerField
from playhouse.reflection import RESERVED_WORDS, generate_models, print_model
from playhouse.migrate import SqliteMigrator, migrate

from types import MethodType

from PyInquirer import prompt, Validator, ValidationError
from collections import OrderedDict

from copy import copy
from tabulate import tabulate

db = SqliteDatabase(None)
migrator = SqliteMigrator(db)
commands = OrderedDict({"Quit": exit})

def push_command(k, v, commands):
  commands[k] = v
  commands.move_to_end(k, last=False)
  # commands.move_to_end("Quit")
  return commands

def create_trigger(func):
  def wrapper(*args, **kwargs):
    # print("args:{}".format(args))
    func(*args, **kwargs)
    trigger_txt = '''
      create trigger if not exists {tbl_name}_set_modified after update on {tbl_name}
      begin
      update {tbl_name} set modified = CURRENT_TIMESTAMP where id = NEW.id;
      end; 
    '''
    db.execute_sql(trigger_txt.format(tbl_name=args[0]._meta.table_name))
    trigger_txt = '''
      CREATE TRIGGER if not exists {tbl_name}_ro_columns
      BEFORE UPDATE OF created ON {tbl_name} when OLD.created != NEW.created
      BEGIN
          SELECT raise(abort, 'can''t change created date!');
      END
    '''
    db.execute_sql(trigger_txt.format(tbl_name=args[0]._meta.table_name))
  return wrapper

class Base(Model):
  name = TextField()
  created = DateTimeField(constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])
  modified = DateTimeField(constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])
  class Meta:
    database = db

def make_model(name, label=None):
  if name in RESERVED_WORDS:
    new_name = name + '_'
    print("'{}' is reserved. Replacing with '{}'.".format(name,new_name))
    name = new_name
  model_name = name
  label = label or name
  attrs = {
    "model_name": model_name,
    "label":label,
    }
  model = type(name, (Base,), attrs)
  # wrap the create_table method to ensure triggers are created immediatley after 
  model.create_table = create_trigger(model.create_table)
  model.create_table = MethodType(model.create_table, model)
  return model

def make_column(model, name, col_cls, col_null, col_default, label=None, fk_cls=None, fk_backref=None ):
  print("col_null: {}".format(col_null))
  if name in RESERVED_WORDS:
    new_name = name + '_'
    print("'{}' is reserved. Replacing with '{}'.".format(name,new_name))
    name = new_name
  column_name = name
  label = label or name
  
  # create instance of col_type
  # TODO: handle specific attributes for each type
  # constraints = []
  # if col_default:
  #   constraints.append(SQL("DEFAULT ?",(col_default,)))
  if col_cls == ForeignKeyField:
    print(fk_cls)
    column = col_cls(fk_cls, null=col_null, field=fk_cls._meta.primary_key, backref=fk_backref, lazy_load=True)
  else:
    column = col_cls(null=col_null, default=col_default)
  migrate(
    migrator.add_column(model._meta.table_name, column_name, column)
  )
  return generate_models(db, table_names=[model._meta.table_name])

# field type to prompt

def prompt_field(commands, field, current_value=None):
  q = {
    "type":"input",
    "name": field.name,
    "message": "{}:".format(field.name),   
  }
  if current_value is not None:
    q.update({"default": current_value})
  a = prompt(q)
  return a[field.name]

def prompt_instance(commands, model_cls, model_instance=None):
  # model_cls = globals().get(model_cls.name)
  # print(model_instance)
  row = model_cls() if model_instance is None else model_instance
  for field in model_cls._meta.sorted_fields:
    if field.field_type != "AUTO" and field.name not in ['created','modified']:
      current_value = getattr(model_instance, field.name, None) if model_instance else None
      if isinstance(current_value, Model):
        current_value = str(getattr(current_value, 'id'))
      new_value = prompt_field(commands, field, current_value=current_value)
      setattr(row, field.name, new_value)
  
  row.save()
  list_instances(model_cls)
  return commands

def prompt_edit(commands, model_cls):
  q={
    "type":"list",
    "name":"name",
    "message": "Select to edit:",
    "choices": [r.name for r in model_cls.select()]
  }
  a = prompt(q)
  model_instance = model_cls.get(model_cls.name==a["name"])
  return prompt_instance(commands, model_cls, model_instance=model_instance)

def list_instances(model_cls):
  # print("list {}".format(model_cls))
  # model_cls = globals().get(model_cls.name)
  # for row in model_cls.select().order_by(model_cls.created).dicts():
  #   print(row)
  print(tabulate(model_cls.select().order_by(model_cls.created).dicts(), headers="keys"))
  return commands

type_to_col_class = {
  "Text" : TextField,
  "Integer": IntegerField,
  "Date and Time": DateTimeField,
  "Lookup": ForeignKeyField
}

def prompt_column(commands, model):
  print_model(model)
  class DefualtRequired(Validator):
    def validate(self, document):
      if len(document.text)==0:
        raise ValidationError(
                  message='Please enter a default value',
                  cursor_position=len(document.text))
  q = [
    {
      "type": "input",
      "name": "col_name",
      "message": "Field name?"
   },
   {
     "type": "list",
     "name": "col_type",
     "message": "Field type?",
     "choices": [ k for k,_ in type_to_col_class.items()]
   },
   {
     "type": "confirm",
     "name": "required",
     "message": "Required (If Y, provide default value)",
     "default": False,
     "when": lambda a: not a["col_type"] == "Lookup"
   },
   {
     "type": "input",
     "name": "default",
     "message": "Default value:",
     "validate": DefualtRequired,
     "when": lambda a: not a["col_type"] == "Lookup" and a["required"]
   },
   {
     "type": "input",
     "name": "default",
     "message": "Default value:",
     "when": lambda a: not a["col_type"] == "Lookup" and not a["required"]
   },
   {
     "type": "list",
     "name": "fk_cls",
     "message": "Lookup to?",
     "choices": [k for k in db.models.keys()],
     "when": lambda a: a["col_type"]=="Lookup",
   },
   {
     "type": "input",
     "name": "fk_backref",
     "message": "Back reference name?",
     "when": lambda a: a["col_type"]=="Lookup", 
   }
  ]
  a = prompt(q)
  col_name = a.get("col_name")
  col_cls = type_to_col_class.get(a.get("col_type"))
  print(a.get('required'))
  col_null = not a.get("required") if a.get("required") is not None else True
  col_default = a.get("default")
  fk_cls = db.models.get(a.get("fk_cls"))
  fk_backref = a.get("fk_backref")
  m = make_column(model, col_name, col_cls, col_null, col_default, fk_cls=fk_cls, fk_backref=fk_backref)
  globals().update(m)
  db.models = m
  print_model(m.get(model._meta.table_name))
  return commands
  
def prompt_model(commands):  
  q = [
    {
      "type": "input",
      "name": "model_name",
      "message": "Model name?"
    }
  ]
  a = prompt(q)
  model_name = a.get("model_name")
  m=make_model(model_name)
  if not m.table_exists():
    m.create_table()
  globals()[m.model_name] = m
  print_model(m)
  commands = push_command(
      "New {} model field".format(model_name), 
      lambda commands: prompt_column(commands, db.models.get(model_name)), 
      commands
  )
  return commands

def add_model_commands(commands, m):
  model_name = m._meta.table_name
  
  commands = push_command(
      "Edit {}".format(model_name),
      lambda commands: prompt_edit(commands, globals().get(model_name)),
      commands
  )
  commands = push_command(
      "New {}".format(model_name),
      lambda commands: prompt_instance(commands, globals().get(model_name)),
      commands
  )
  commands = push_command(    
    "List {}s".format(model_name),
    lambda commands: list_instances(globals().get(model_name)),
    commands
  )
  return commands

def cons_menu(commands):
  prev = copy(commands)
  commands = OrderedDict({"Back": lambda commands: prev})
  commands = push_command(
    "New Model",
    prompt_model, 
    commands)
  for m in db.models.values():
    model_name = m._meta.table_name
    commands = push_command(
      "New {} model field".format(model_name), 
      lambda commands: prompt_column(commands, db.models.get(model_name)), 
      commands
  )
  return commands

def data_menu(commands, model):
  prev = copy(commands)
  commands = OrderedDict({"Back": lambda commands: prev})
  commands = add_model_commands(commands, model)
  return commands

def prompt_db(commands):
  q = [
    {
      "type": "input",
      "name": "file_name",
      "message": "Crate name"
    }
  ]
  a = prompt(q)
  # print(a)
  db.init(a.get("file_name"))
  commands = push_command(
    "Construct",
    cons_menu, 
    commands)
  models = generate_models(db)
  db.models = models
  for name, model in models.items():
    print_model(model)
    # add_model_commands(commands, model)
    commands = push_command(name, open_data_menu(commands, name), commands)
  globals().update(models)
  if len(db.get_tables()) == 0:
    print("Hmm. This crate appears to be empty. Try making a new model.")
  return commands
def open_data_menu(commands, name):
  return lambda commands: data_menu(commands, db.models.get(name))
commands = push_command(
  "Open Crate", 
  prompt_db, 
  commands)

def get_cmd_list(commands):
  return [
    k for k,_ in commands.items()
  ]

main_menu = {
  "type": "list",
  "name": "cmd",
  "message": "Select:",
  "choices": get_cmd_list(commands)
}

print("CrateD 0.0.1")
while True:
  print("Current Crate: {}".format(db.database))
  key = prompt(main_menu).get("cmd")
  if key != "Quit":
    # print(key)
    if key is not None:
      commands=commands.get(key)(commands)
    # update our choices in case commands have changed 
    main_menu["choices"] = get_cmd_list(commands) 
  else:
    break