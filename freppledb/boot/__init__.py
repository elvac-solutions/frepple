#
# Copyright (C) 2017 by frePPLe bv
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero
# General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""
The boot app is placed at the top of the list in ``INSTALLED_APPS``
for the purpose of hooking into Django's ``class_prepared`` signal
and defining attribute fields.

This app is very closely inspired on http://mezzanine.jupo.org/
and its handling of injected extra fields.
"""
import copy
import os
from importlib import import_module
from itertools import chain

from django.conf import settings
from django.db import models

from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.db import connections
from django.db.models.signals import class_prepared
from django.db.utils import DEFAULT_DB_ALIAS

from freppledb.common.fields import JSONBField


_register = {}
_register_kwargs = {}


def add_extra_model_fields(sender, **kwargs):
    model_path = "%s.%s" % (sender.__module__, sender.__name__)
    for field_name, label, fieldtype, editable, initially_hidden in chain(
        _register.get(model_path, []), _register.get(sender._meta.db_table, [])
    ):

        register_args = (
            _register_kwargs[(model_path, field_name)]
            if (model_path, field_name) in _register_kwargs
            else None
        )

        if fieldtype == "string":
            if register_args and "max_length" in register_args:
                max_length = register_args["max_length"]
            else:
                max_length = 300
            field = models.CharField(
                label,
                max_length=max_length,
                null=True,
                blank=True,
                db_index=True,
                editable=editable,
            )
        elif fieldtype == "boolean":
            field = models.NullBooleanField(
                label, null=True, blank=True, db_index=True, editable=editable
            )
        elif fieldtype == "number":
            # Note: Other numeric fields have precision 20, 8.
            # Changing the value below would require migrating existing attributes of all projects.
            if register_args:
                max_digits = register_args.get("max_digits", 15)
                decimal_places = register_args.get("decimal_places", 6)
            else:
                max_digits = 15
                decimal_places = 6
            field = models.DecimalField(
                label,
                max_digits=max_digits,
                decimal_places=decimal_places,
                null=True,
                blank=True,
                db_index=True,
                editable=editable,
            )
        elif fieldtype == "integer":
            field = models.IntegerField(
                label, null=True, blank=True, db_index=True, editable=editable
            )
        elif fieldtype == "date":
            field = models.DateField(
                label, null=True, blank=True, db_index=True, editable=editable
            )
        elif fieldtype == "datetime":
            field = models.DateTimeField(
                label, null=True, blank=True, db_index=True, editable=editable
            )
        elif fieldtype == "duration":
            field = models.DurationField(
                label, null=True, blank=True, db_index=True, editable=editable
            )
        elif fieldtype == "time":
            field = models.TimeField(
                label, null=True, blank=True, db_index=True, editable=editable
            )
        elif fieldtype == "jsonb":
            field = JSONBField(default="{}", null=True, blank=True, editable=editable)
        else:
            raise ImproperlyConfigured("Invalid attribute type '%s'." % fieldtype)
        field.contribute_to_class(sender, field_name)


def registerAttribute(model, attrlist, **kwargs):
    """
    Register a new attribute.
    The attribute list is passed as a list of tuples in the format
      fieldname, label, fieldtype, editable (default=True), initially_hidden (default=False)
    """
    if model not in _register:
        _register[model] = []
    for attr in attrlist:
        if len(attr) < 3:
            raise Exception("Invalid attribute definition: %s" % attr)
        elif len(attr) == 3:
            _register[model].append(attr + (True, False))
        elif len(attr) == 4:
            _register[model].append(attr + (False,))
        else:
            _register[model].append(attr)

        if kwargs:
            _register_kwargs[(model, attr[0])] = kwargs


def getAttributes(model):
    """
    Return all attributes for a given model in the format:
      fieldname, label, fieldtype, editable (default=True), initially_hidden (default=False)
    """
    for attr in chain(
        _register.get("%s.%s" % (model.__module__, model.__name__), []),
        _register.get(model._meta.db_table, []),
    ):
        yield attr
    for base in model.__bases__:
        if hasattr(base, "_meta"):
            for attr in getAttributes(base):
                yield attr


def getAttributeFields(model, related_name_prefix=None, initially_hidden=False):
    """
    Return report fields for all attributes of a given model.
    """
    from freppledb.common.report import GridFieldText, GridFieldBool, GridFieldNumber
    from freppledb.common.report import (
        GridFieldInteger,
        GridFieldDate,
        GridFieldDateTime,
    )
    from freppledb.common.report import GridFieldDuration, GridFieldTime

    result = []
    for field_name, label, fieldtype, editable, hidden in getAttributes(model):
        if related_name_prefix:
            field_name = "%s__%s" % (related_name_prefix, field_name)
            label = "%s - %s" % (related_name_prefix.split("__")[-1], label)
        else:
            label = "%s - %s" % (model.__name__, label)
        if fieldtype == "string":
            result.append(
                GridFieldText(
                    field_name,
                    title=label,
                    initially_hidden=hidden or initially_hidden,
                    editable=editable,
                )
            )
        elif fieldtype == "boolean":
            result.append(
                GridFieldBool(
                    field_name,
                    title=label,
                    initially_hidden=hidden or initially_hidden,
                    editable=editable,
                )
            )
        elif fieldtype == "number":
            result.append(
                GridFieldNumber(
                    field_name,
                    title=label,
                    initially_hidden=hidden or initially_hidden,
                    editable=editable,
                )
            )
        elif fieldtype == "integer":
            result.append(
                GridFieldInteger(
                    field_name,
                    title=label,
                    initially_hidden=hidden or initially_hidden,
                    editable=editable,
                )
            )
        elif fieldtype == "date":
            result.append(
                GridFieldDate(
                    field_name,
                    title=label,
                    initially_hidden=hidden or initially_hidden,
                    editable=editable,
                )
            )
        elif fieldtype == "datetime":
            result.append(
                GridFieldDateTime(
                    field_name,
                    title=label,
                    initially_hidden=hidden or initially_hidden,
                    editable=editable,
                )
            )
        elif fieldtype == "duration":
            result.append(
                GridFieldDuration(
                    field_name,
                    title=label,
                    initially_hidden=hidden or initially_hidden,
                    editable=editable,
                )
            )
        elif fieldtype == "time":
            result.append(
                GridFieldTime(
                    field_name,
                    title=label,
                    initially_hidden=hidden or initially_hidden,
                    editable=editable,
                )
            )
        elif fieldtype == "jsonb":
            result.append(
                GridFieldText(
                    field_name,
                    title=label,
                    initially_hidden=hidden or initially_hidden,
                    editable=editable,
                )
            )
        else:
            raise Exception("Invalid attribute type '%s'." % fieldtype)
    return result


def addAttributesFromDatabase():
    # Read attributes defined in the default database
    from django.conf import settings

    database_type_mapping = {
        "string": ("character varying", "(300)"),
        "boolean": ("boolean", ""),
        "number": ("numeric", "(15,6)"),
        "integer": ("integer", ""),
        "date": ("date", ""),
        "datetime": ("timestamp with time zone", ""),
        "duration": ("interval", ""),
        "time": ("time without time zone", ""),
        "jsonb": ("jsonb", ""),
    }

    if "FREPPLE_TEST" in os.environ:
        for db in settings.DATABASES:
            settings.DATABASES[db]["NAME"] = settings.DATABASES[db]["TEST"]["NAME"]

    try:
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute(
                """
                select 
                  model, name, label, type, editable, initially_hidden
                from common_attribute
                """
            )
            attributes = {}
            for x in cursor.fetchall():
                table = x[0]
                if table in attributes:
                    attributes[table].append((x[1], x[2], x[3], x[4], x[5]))
                else:
                    attributes[table] = [
                        (x[1], x[2], x[3], x[4], x[5]),
                    ]

            # Loop over all scenarios
            cursor.execute(
                """
                select name 
                from common_scenario 
                where status='In use' or name = %s
                """,
                (DEFAULT_DB_ALIAS,),
            )
            scenariolist = [i[0] for i in cursor.fetchall()]
            if not scenariolist:
                scenariolist = [
                    DEFAULT_DB_ALIAS,
                ]
            for scenario in scenariolist:
                with connections[scenario].cursor() as cursor2:
                    attr_list = copy.deepcopy(attributes)

                    # Pick up all existing attribute fields
                    cursor2.execute(
                        """
                        select c.table_name, c.column_name, 
                        c.data_type
                        from pg_catalog.pg_statio_all_tables as st
                        inner join pg_catalog.pg_description pgd 
                        on pgd.objoid=st.relid
                        inner join information_schema.columns c 
                        on pgd.objsubid=c.ordinal_position
                        and  c.table_schema=st.schemaname and c.table_name=st.relname
                        where st.schemaname = 'public'
                        and pgd.description = 'Custom attribute'
                        """
                    )
                    attr_existing = {}
                    for m, c, t in cursor2.fetchall():
                        if m not in attr_existing:
                            attr_existing[m] = {}
                        attr_existing[m][c] = t

                    # Delete attribute fields that have changed type or no longer exist
                    for model, cols in attr_existing.items():
                        for col, fldtype in cols.items():
                            to_delete = True
                            for fld in attr_list.get(model, []):
                                if (
                                    fld[0] == col
                                    and database_type_mapping.get(fld[2], ("",))[0]
                                    == fldtype
                                ):
                                    to_delete = False
                            if to_delete:
                                cursor2.execute(
                                    """
                                    alter table "%s" drop column "%s";
                                    """
                                    % (
                                        model,
                                        col,
                                    )
                                )

                    # Pick up all database fields
                    cursor2.execute(
                        """
                        select table_name, column_name
                        from information_schema.columns cols
                        where table_schema = 'public'
                        and table_name in (
                        select table_name
                        from information_schema.tables
                        where table_schema = 'public' and table_type = 'BASE TABLE'
                        )
                        """
                    )
                    model_fields = {}
                    for m, c in cursor2.fetchall():
                        if m in model_fields:
                            model_fields[m].append(c)
                        else:
                            model_fields[m] = [c]

                    for model, cols in attr_list.items():
                        for col in cols:
                            if (
                                col[0] not in model_fields.get(model, [])
                                or col[0] in attr_existing.get(model, {})
                                and scenario == DEFAULT_DB_ALIAS
                            ):
                                if model not in _register:
                                    _register[model] = []
                                _register[model].append(col)
                            if col[0] not in model_fields.get(model, []):
                                cursor2.execute(
                                    """
                                    alter table "%s"
                                    add column "%s" %s%s;

                                    comment on column "%s"."%s" is 'Custom attribute';

                                    create index on "%s" ("%s")
                                    """
                                    % (
                                        model,
                                        col[0],
                                        database_type_mapping[col[2]][0],
                                        database_type_mapping[col[2]][1],
                                        model,
                                        col[0],
                                        model,
                                        col[0],
                                    )
                                )
    except Exception as e:
        # Database or attribute table may not exist yet.
        pass


_first = True
if _first:
    _first = False
    # Scan attribute definitions from the settings
    for model, attrlist in settings.ATTRIBUTES:
        registerAttribute(model, attrlist)

    # Scan attribute definitions from the installed apps
    for app in reversed(settings.INSTALLED_APPS):
        try:
            mod = import_module("%s.attributes" % app)
        except ImportError as e:
            # Silently ignore if it's the menu module which isn't found
            if str(e) not in (
                "No module named %s.attributes" % app,
                "No module named '%s.attributes'" % app,
            ):
                raise e

    # Scan attribute definitions from the installed apps
    addAttributesFromDatabase()

    if _register:
        class_prepared.connect(
            add_extra_model_fields, dispatch_uid="frepple_attribute_injection"
        )
