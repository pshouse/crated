# import pickle
# import pickletools
from peewee import (Model, SqliteDatabase, BlobField, TextField, IntegerField, DateField, DateTimeField, ForeignKeyField, BooleanField, SQL)
# import dill as pickle
from cloudpickle import dumps, loads
# from objgraph import show_refs
from playhouse.migrate import SqliteMigrator, migrate
# from playhouse.reflection import print_model, print_table_sql
import logging
from collections import OrderedDict
from types import MethodType

logger = logging.getLogger('peewee')
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.ERROR)

type_to_fld_cls = {
  "Text" : TextField,
  "Integer": IntegerField,
  "Checkbox": BooleanField,
  'Date': DateField,
  "Date and Time": DateTimeField,
  "Lookup": ForeignKeyField
}
# db_proxy = DatabaseProxy()
db = SqliteDatabase(None, pragmas={'foreign_keys': 1})
migrator = SqliteMigrator(db)
app_models = OrderedDict()
# class test():
#   pass

# class mCrated(ModelBase):
  # pass

class Base(Model):
  name = TextField()
  created = DateTimeField(constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])
  modified = DateTimeField(constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])
  class Meta:
    database=db

class Metadata(Base):
  models = BlobField() 

def create_trigger(func):
  def wrapper(*args, **kwargs):
    # print("args:{}".format(args))
    func(*args, **kwargs)
    trigger_txt = '''
      create trigger if not exists {tbl_name}_set_{col_name} after update on {tbl_name}
      begin
      update {tbl_name} set modified = {expression} where id = NEW.id;
      end; 
    '''
    db.execute_sql(trigger_txt.format(tbl_name=args[0]._meta.table_name, col_name='modified', expression="CURRENT_TIMESTAMP"))
    trigger_txt = '''
      CREATE TRIGGER if not exists {tbl_name}_ro_{col_name}
      BEFORE UPDATE OF created ON {tbl_name} when OLD.{col_name} != NEW.{col_name}
      BEGIN
          SELECT raise(abort, 'can''t change {col_name}!');
      END
    '''
    db.execute_sql(trigger_txt.format(tbl_name=args[0]._meta.table_name, col_name="created"))
  return wrapper

def make_model(name):
  name = name.lower()
  mdl_cls = type(name, (Base, ), {})
  app_models.update( { name : {'fields': []} } )
  md = Metadata.get_by_id(1)
  md.models = dumps(app_models)
  md.save()

  # ensure db triggers for audit fields are created
  mdl_cls.create_table = create_trigger(mdl_cls.create_table)
  mdl_cls.create_table = MethodType(mdl_cls.create_table, mdl_cls)

  if not mdl_cls.table_exists():
    mdl_cls.create_table()
  db.models[name] = mdl_cls
  return mdl_cls

def make_field(mdl_cls, name, fld_type, fld_null, fld_default, fld_label=None, fk_type=None, fk_backref=None, column_name=None, **kwargs):
  fld_cls = type_to_fld_cls[fld_type]
  
  if fld_cls == ForeignKeyField:
    if fk_type not in db.models:
      make_model(fk_type)
    fk_mdl = db.models[fk_type]
    fld = fld_cls(fk_mdl, null=fld_null, field=fk_mdl._meta.primary_key, backref=fk_backref, lazy_load=True, column_name=column_name, **kwargs)
    # print("column_name: {}".format(fld.column_name))
  else:
    fld = fld_cls(null=fld_null, default=fld_default, **kwargs)
  kwargs.update({'fld_label':fld_label, 'fk_type': fk_type, 'fk_backref': fk_backref, 'column_name' : name})
  fld_md = ((name, fld_type, fld_null, fld_default),kwargs)
  app_models[mdl_cls._meta.name]['fields'].append(fld_md)
  md = Metadata.get_by_id(1)
  md.models = dumps(app_models)
  md.save()
  col_names = [col.name for col in db.get_columns(mdl_cls._meta.table_name)]
  if name not in col_names:    
    migrate(
      migrator.add_column(mdl_cls._meta.name, name, fld)
    )
  mdl_cls._meta.add_field(name, fld)
  # print('name: {}'.format(name) )
  # print("column_name: {}".format(fld.column_name))
  db.models[mdl_cls._meta.name] = mdl_cls
  return mdl_cls

def delete_model(mdl_cls):
  mdl_cls.drop_table()
  db.models.pop(mdl_cls._meta.name)
  app_models.pop(mdl_cls._meta.name)
  md = Metadata.get_by_id(1)
  md.models = dumps(app_models)
  md.save()

def open_database(filename):
  db.init(filename)
  if Metadata.table_exists() and Metadata.select().count() > 0:
    metadata = Metadata.get_by_id(1)
    models = OrderedDict()
    db.models = OrderedDict()
    app_models.update ( loads(metadata.models) )
    for n,data in app_models.items():
      mdl_cls = make_model(n)
      for fld in data['fields']:
        make_field(mdl_cls, *fld[0], **fld[1])
      models[n] = mdl_cls      
  else:
    Metadata.create_table()
    # models = generate_models(db)
    models = OrderedDict()
    Metadata.create(name='models',models=dumps(models))
  db.models = models

def setup():
  dog = make_model('dog')
  toy = make_model('toy')
  toy = make_field(toy, 'dog', 'Lookup', True, None,
    fk_type='dog', fk_backref='toys')
  sam = dog.create(name='Sam')
  duck = toy.create(name='duck', dog=1)
  return (dog, toy, sam, duck)

# d = mCrated('dog',(Base, ), {})
# show_refs(d, filename='mCrated.dog.png')
# open_database('test')