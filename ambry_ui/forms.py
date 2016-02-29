""" User Forms

Copyright (c) 2015 Civic Knowledge. This file is licensed under the terms of
the Revised BSD License, included in this distribution as LICENSE.txt
"""


from flask_wtf import Form
from wtforms.fields import StringField, PasswordField
from wtforms.validators import Required, DataRequired, Email
from wtforms import BooleanField, TextField, PasswordField, validators, RadioField


class LoginForm(Form):
    username = StringField('Username', [validators.Length(min=3, max=25)])
    password = PasswordField('New Password', [validators.DataRequired()])

    def validate_csrf_token(self, field):
        return super(LoginForm, self).validate_csrf_token(field)


class NewUserForm(Form):
    username = StringField('name', validators=[DataRequired(), validators.Length(min=3, max=25)])
    password = PasswordField('password', validators=[DataRequired(), validators.Length(min=6, max=25)])
    account_type = RadioField(choices=[('admin','admin'),('user','user')], default='user')


class AddBundleForm(Form):
    ref = StringField('ref', validators=[DataRequired(), validators.Length(min=3, max=25)])
