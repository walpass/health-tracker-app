from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, FloatField, TextAreaField, IntegerField # FloatField, TextAreaField, IntegerField, Optional, dateを追加 (app.pyで使用しているフィールドを想定して追加)
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Optional # Optional, DataRequired, Length, Email, EqualTo, ValidationErrorをインポート済みか確認
from datetime import date # dateフィルター用にインポート (もしRecordFormなどで日付を使っている場合)

# forms.pyではUserモデルをインポートしません。
# Userモデルに依存するバリデーションはapp.pyのルート関数内で行います。

class RegistrationForm(FlaskForm):
    username = StringField('ユーザー名',
                           validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('メールアドレス',
                        validators=[DataRequired(), Email()])
    password = PasswordField('パスワード',
                             validators=[DataRequired()])
    confirm_password = PasswordField('パスワード（確認）',
                                     validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('登録')

    # ユーザー名とメールアドレスの重複チェックはapp.pyのregisterルートに移動しました。
    # ここではカスタムバリデーションメソッドを削除します。
    # def validate_username(self, username):
    #     pass
    # def validate_email(self, email):
    #     pass


class LoginForm(FlaskForm):
    email = StringField('メールアドレス',
                        validators=[DataRequired(), Email()])
    password = PasswordField('パスワード',
                             validators=[DataRequired()])
    remember_me = BooleanField('ログイン情報を記憶する') # ★ここを 'remember_me' に修正しました★
    submit = SubmitField('ログイン')

class GroupForm(FlaskForm):
    name = StringField('グループ名', validators=[DataRequired(), Length(min=2, max=80)])
    submit = SubmitField('グループ作成')

class AddMemberForm(FlaskForm):
    # メンバーを検索するためのフィールド（ユーザー名またはメールアドレス）
    search_query = StringField('メンバーのユーザー名またはメールアドレス',
                               validators=[DataRequired(), Length(min=1, max=120)])
    submit = SubmitField('メンバーを招待（追加）')


# 補足: もしRecordFormなどがforms.pyに存在する場合、それらのフィールドも正しくインポートされているか確認してください。
# 例:
# class RecordForm(FlaskForm):
#     date = StringField('日付', validators=[DataRequired()])
#     weight = FloatField('体重 (kg)', validators=[DataRequired()])
#     height = FloatField('身長 (cm)', validators=[Optional()]) # Optionalのインポートが必要
#     notes = TextAreaField('メモ', validators=[Length(max=500), Optional()])
#     submit = SubmitField('記録')