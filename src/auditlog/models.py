import json

from django.conf import settings
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import ugettext_lazy as _

from .middleware import get_current_user, get_current_ip, get_current_path


class LogEntryManager(models.Manager):
    """
    Custom manager for the LogEntry model.
    """

    def log_create(self, instance, **kwargs):
        """
        Helper method to create a new log entry. This method automatically fills in some data when it is left out. It
        was created to keep things DRY.
        """
        changes = kwargs.get('changes', None)
        pk = self._get_pk_value(instance)

        if changes is not None:
            kwargs.setdefault('content_type', ContentType.objects.get_for_model(instance))
            kwargs.setdefault('object_pk', pk)
            kwargs.setdefault('object_repr', str(instance))

            if isinstance(pk, int):
                kwargs.setdefault('object_id', pk)

            # Delete log entries with the same pk as a newly created model. This should only be necessary when an pk is
            # used twice.
            if kwargs.get('action', None) is LogEntry.Action.CREATE:
                if kwargs.get('object_id', None) is not None and self.filter(content_type=kwargs.get('content_type'), object_id=kwargs.get('object_id')).exists():
                    self.filter(content_type=kwargs.get('content_type'), object_id=kwargs.get('object_id')).delete()
                else:
                    self.filter(content_type=kwargs.get('content_type'), object_pk=kwargs.get('object_pk', '')).delete()

            return self.create(**kwargs)
        return None

    def get_for_object(self, instance):
        """
        Get log entries for the specified object.
        """
        content_type = ContentType.objects.get_for_model(instance.__class__)
        pk = self._get_pk_value(instance)

        if isinstance(pk, int):
            return self.filter(content_type=content_type, object_id=pk)
        else:
            return self.filter(content_type=content_type, object_pk=pk)

    def get_for_model(self, model):
        """
        Get log entries for all objects of a specified type.
        """
        content_type = ContentType.objects.get_for_model(model)
        return self.filter(content_type=content_type)

    def _get_pk_value(self, instance):
        """
        Get the primary key field value for a model instance.
        """
        pk_field = instance._meta.pk.name
        return getattr(instance, pk_field, None)


class LogEntry(models.Model):
    """
    Represents an entry in the audit log. The content type is saved along with the textual and numeric (if available)
    primary key, as well as the textual representation of the object when it was saved. It holds the action performed
    and the fields that were changed in the transaction.

    If AuditlogMiddleware is used, the actor will be set automatically. Keep in mind that editing / re-saving LogEntry
    instances may set the actor to a wrong value - editing LogEntry instances is not recommended (and it should not be
    necessary).
    """

    class Action:
        CREATE = 0
        UPDATE = 1
        DELETE = 2

        choices = (
            (CREATE, _("create")),
            (UPDATE, _("update")),
            (DELETE, _("delete")),
        )

    content_type = models.ForeignKey('contenttypes.ContentType', on_delete=models.CASCADE, related_name='+', verbose_name=_("content type"))
    object_pk = models.TextField(verbose_name=_("object pk"))
    object_id = models.PositiveIntegerField(blank=True, db_index=True, null=True, verbose_name=_("object id"))
    object_repr = models.TextField(verbose_name=_("object representation"))
    action = models.PositiveSmallIntegerField(choices=Action.choices, verbose_name=_("action"))
    changes = models.TextField(blank=True, verbose_name=_("change message"))
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.SET_NULL, related_name='+', default=get_current_user, verbose_name=_("actor"))
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name=_("timestamp"))
    ip_address = models.GenericIPAddressField(blank=True, null=True, unpack_ipv4=True, default=get_current_ip, verbose_name=_("ip address"))
    request_path = models.CharField(max_length=255, blank=True, default=get_current_path, verbose_name=_("path"))

    objects = LogEntryManager()

    class Meta:
        get_latest_by = 'timestamp'
        ordering = ['-timestamp']
        verbose_name = _("log entry")
        verbose_name_plural = _("log entries")

    def __unicode__(self):
        if self.action == self.Action.CREATE:
            fstring = _("Created {repr:s}")
        elif self.action == self.Action.UPDATE:
            fstring = _("Updated {repr:s}")
        elif self.action == self.Action.DELETE:
            fstring = _("Deleted {repr:s}")
        else:
            fstring = _("Logged {repr:s}")

        return fstring.format(repr=self.object_repr)

    @property
    def changes_dict(self):
        """
        Return the changes recorded in this log entry as a dictionary object.
        """
        try:
            return json.loads(self.changes)
        except ValueError:
            return {}

    @property
    def changes_str(self, colon=': ', arrow=u' \u2192 ', separator='; '):
        """
        Return the changes recorded in this log entry as a string. The formatting of the string can be customized by
        setting alternate values for colon, arrow and separator. If the formatting is still not satisfying, please use
        changes_dict() and format the string yourself.
        """
        substrings = []

        for field, values in self.changes_dict.iteritems():
            substring = u'{field_name:s}{colon:s}{old:s}{arrow:s}{new:s}'.format(
                field_name=field,
                colon=colon,
                old=values[0],
                arrow=arrow,
                new=values[1],
            )
            substrings.append(substring)

        return separator.join(substrings)


class AuditlogHistoryField(generic.GenericRelation):
    """
    A subclass of django.contrib.contenttypes.generic.GenericRelation that sets some default variables. This makes it
    easier to implement the audit log in models, and makes future changes easier.

    By default this field will assume that your primary keys are numeric, simply because this is the most common case.
    However, if you have a non-integer primary key, you can simply pass pk_indexable=False to the constructor, and
    Auditlog will fall back to using a non-indexed text based field for this model.
    """

    def __init__(self, pk_indexable=True, **kwargs):
        kwargs['to'] = LogEntry

        if pk_indexable:
            kwargs['object_id_field'] = 'object_id'
        else:
            kwargs['object_id_field'] = 'object_pk'

        kwargs['content_type_field'] = 'content_type'
        super(AuditlogHistoryField, self).__init__(**kwargs)
