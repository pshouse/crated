from peewee import Model, SqliteDatabase, TextField, DateTimeField, SQL, ForeignKeyField, IntegerField, DateField, BlobField, buffer_type
from playhouse.reflection import RESERVED_WORDS, generate_models, print_model, DatabaseProxy

from PyInquirer import prompt, Validator, ValidationError
from collections import OrderedDict

from copy import copy
from tabulate import tabulate

from crated import make_model, make_field, app_models, db, type_to_fld_cls, open_database

def push_command(k, v, commands):
  commands[k] = v
  commands.move_to_end(k, last=False)
  return commands


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
  row = model_cls() if model_instance is None else model_instance
  for field in model_cls._meta.sorted_fields:
    if field.field_type != "AUTO" and field.name not in ['created','modified']:
      current_value = getattr(model_instance, field.name, None) if model_instance else None
      if isinstance(current_value, Model):
        current_value = str(getattr(current_value, 'id'))
      new_value = prompt_field(commands, field, current_value=current_value)
      if isinstance(field, (ForeignKeyField,IntegerField)) and new_value == '':
        new_value = None
      setattr(row, field.name, new_value) 
  row.save()
  list_instances(commands, model_cls)
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

def list_instances(commands, model_cls):
  print(tabulate(model_cls.select().order_by(model_cls.created).dicts(), headers="keys"))
  return commands

def prompt_column(commands, model):
  model = db.models.get(model)
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
      "message": "Field name (empty=cancel)?"
   },
   {
     "type": "list",
     "name": "col_type",
     "message": "Field type?",
     "choices": [ k for k,_ in type_to_fld_cls.items()],
     "when": lambda a: a['col_name'] != ''
   },
   {
     "type": "confirm",
     "name": "required",
     "message": "Required (If Y, provide default value)",
     "default": False,
     "when": lambda a: a['col_name'] != '' and not a["col_type"] == "Lookup"
   },
   {
     "type": "input",
     "name": "default",
     "message": "Default value:",
     "validate": DefualtRequired,
     "when": lambda a: a['col_name'] != '' and not a["col_type"] == "Lookup" and a["required"]
   },
   {
     "type": "input",
     "name": "default",
     "message": "Default value:",
     "when": lambda a: a['col_name'] != '' and not a["col_type"] == "Lookup" and not a["required"]
   },
   {
     "type": "list",
     "name": "fk_cls",
     "message": "Lookup to?",
     "choices": [k for k in db.models.keys()],
     "when": lambda a: a['col_name'] != '' and a["col_type"]=="Lookup",
   },
   {
     "type": "input",
     "name": "fk_backref",
     "message": "Back reference name?",
     "when": lambda a: a['col_name'] != '' and a["col_type"]=="Lookup", 
   }
  ]
  a = prompt(q)
  col_name = a.get("col_name")   
  if col_name != '':
    fld_type = a.get("col_type")
    print(a.get('required'))
    col_null = not a.get("required") if a.get("required") is not None else True
    col_default = a.get("default")
    fk_type = a.get("fk_cls")
    fk_backref = a.get("fk_backref")
    m = make_field(model, col_name, fld_type, col_null, col_default, fk_type=fk_type, fk_backref=fk_backref)
    print_model(m)
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
  
  commands = update_model_commands(commands)
  return commands

def cons_menu(commands):
  prev = copy(commands)
  commands = OrderedDict({"Back": lambda commands: update_data_commands(prev)})
  commands = push_command(
    "New Model",
    prompt_model, 
    commands)
  commands = update_model_commands(commands)
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
  open_database((a.get("file_name")))
  commands = push_command(
    "Construct",
    cons_menu, 
    commands)

  commands = update_data_commands(commands)
  if len(db.get_tables()) == 1:
    print("Hmm. This crate appears to be empty. Try making a new model.")
  return commands

def update_data_commands(commands):
  for name, model in db.models.items():
    print_model(model)
    commands = push_command(name, open_data_menu(commands, name), commands)
  return commands

def open_data_menu(commands, name):
  return lambda commands: data_menu(commands, db.models.get(name))

def data_menu(commands, model):
  prev = copy(commands)
  commands = OrderedDict({"Back": lambda commands: prev})
  commands = add_data_commands(commands, model)
  return commands

def add_data_commands(commands, m):
  model_name = m._meta.table_name
  commands = push_command(
      "Edit {}".format(model_name),
      lambda commands: prompt_edit(commands, db.models.get(model_name)),
      commands
  )
  commands = push_command(
      "New {}".format(model_name),
      lambda commands: prompt_instance(commands, db.models.get(model_name)),
      commands
  )
  commands = push_command(    
    "List {}s".format(model_name),
    lambda commands: list_instances(commands, db.models.get(model_name)),
    commands
  )
  return commands

def update_model_commands(commands):
  for name, model in db.models.items():
    print_model(model)
    commands = push_command("{} model".format(name), open_model_menu(commands, name), commands)
  return commands

def open_model_menu(commands, name):
  return lambda commands: model_menu(commands, db.models.get(name))

def model_menu(commands, model):
  prev = copy(commands)
  commands = OrderedDict({"Back": lambda commands: prev})
  commands = add_model_commands(commands, model)
  return commands

def add_model_commands(commands, m):
  model_name = m._meta.table_name
  commands = push_command(
      "Edit {} model".format(model_name),
      lambda commands: prompt_edit_model(commands, db.models.get(model_name)),
      commands
  )
  commands = push_command(
      "New {} model field".format(model_name),
      lambda commands: prompt_column(commands, model_name),
      commands
  )
  commands = push_command(    
    "View {} model".format(model_name),
    lambda commands: view_model(commands, model_name),
    commands
  )
  return commands

def prompt_edit_model(commands, model):
  print("not implemented")
  return commands

def view_model(commands, name):
  print_model(db.models.get(name))
  return commands

def get_cmd_list(commands):
  return [
    k for k,_ in commands.items()
  ]

def main():
  commands = OrderedDict({"Quit": exit})
  commands = push_command(
    "Open Crate", 
    prompt_db, 
    commands)

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
      if key is not None:
        commands=commands.get(key)(commands)
      main_menu["choices"] = get_cmd_list(commands) 
    else:
      break

if __name__ == '__main__':
  main()