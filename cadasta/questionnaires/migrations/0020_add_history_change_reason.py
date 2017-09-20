# -*- coding: utf-8 -*-
# Generated by Django 1.10.7 on 2017-08-09 06:52
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('questionnaires', '0019_add_gps_accuracy'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalquestion',
            name='history_change_reason',
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='historicalquestiongroup',
            name='history_change_reason',
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='historicalquestionnaire',
            name='history_change_reason',
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='historicalquestionoption',
            name='history_change_reason',
            field=models.CharField(max_length=100, null=True),
        ),
    ]