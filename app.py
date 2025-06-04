import os
from datetime import datetime, timedelta
from flask import Flask, render_template, url_for, flash, redirect, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
import plotly.express as px
import pandas as pd
import numpy as np

# Flaskアプリケーションの初期化
app = Flask(__name__)

# データベースURIを環境変数から取得、なければSQLiteを使用
# Renderにデプロイする場合はDATABASE_URL環境変数が使われる
# ローカルで開発する場合はsqlite:///site.dbが使われる
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///site.db')

# SECRET_KEYも環境変数から取得するように変更
# 'your_fallback_secret_key_here' の部分には、ローカルで開発していた際に使っていた
# 実際のSECRET_KEYと同じ文字列を、念のためそのまま残しておくと良いでしょう。
# 例: app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ここにはあなたが以前生成した長いSECRET_KEYをペースト')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'b2686229b2e901ce32cde29c08627e93e6fb28e2ed732a7b') # Replace with a strong, random key

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login' # ログインが必要な場合にリダイレクトされるビュー

# ユーザーモデル
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    records = db.relationship('HealthRecord', backref='author', lazy=True)

    def __repr__(self):
        return f"User('{self.username}', '{self.email}')"

# 健康記録モデル
class HealthRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    weight = db.Column(db.Float, nullable=False)
    height = db.Column(db.Float, nullable=True) # 身長を追加
    bmi = db.Column(db.Float, nullable=True) # BMIを追加
    notes = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"HealthRecord('{self.weight}', '{self.date}')"

    def calculate_bmi(self):
        if self.weight and self.height:
            # 身長をメートルに変換
            height_m = self.height / 100
            self.bmi = round(self.weight / (height_m ** 2), 2)
        else:
            self.bmi = None


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ホームページ
@app.route("/")
@app.route("/home")
def home():
    return render_template('home.html', title='Home')

# ユーザー登録
@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256') # pbkdf2:sha256に変更
        user = User(username=username, email=email, password=hashed_password)
        try:
            db.session.add(user)
            db.session.commit()
            flash('アカウントが作成されました！ログインしてください。', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'登録に失敗しました: {e}', 'danger')
            app.logger.error(f"Registration error: {e}") # ログ出力
    return render_template('register.html', title='Register')

# ログイン
@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)
            return redirect(url_for('dashboard'))
        else:
            flash('ログインに失敗しました。メールアドレスまたはパスワードを確認してください。', 'danger')
    return render_template('login.html', title='Login')

# ログアウト
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

# ダッシュボード
@app.route("/dashboard")
@login_required
def dashboard():
    # ユーザーの健康記録を取得（新しい順）
    records = HealthRecord.query.filter_by(user_id=current_user.id).order_by(HealthRecord.date.desc()).all()

    # グラフデータ準備
    dates = [record.date for record in records]
    weights = [record.weight for record in records]
    bmis = [record.bmi for record in records]

    # pandas DataFrameに変換
    df_weight = pd.DataFrame({'Date': dates, 'Weight': weights})
    df_bmi = pd.DataFrame({'Date': dates, 'BMI': bmis})

    # NaNを含む行を除外（BMIが計算されていない場合など）
    df_bmi = df_bmi.dropna(subset=['BMI'])

    # グラフの生成
    weight_graph_html = ""
    bmi_graph_html = ""

    if not df_weight.empty:
        # 日付でソート（古い日付から新しい日付へ）
        df_weight = df_weight.sort_values(by='Date')
        fig_weight = px.line(df_weight, x='Date', y='Weight', title='体重の推移')
        fig_weight.update_xaxes(
            rangeselector=dict(
                buttons=list([
                    dict(count=7, label="1w", step="day", stepmode="backward"),
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(count=3, label="3m", step="month", stepmode="backward"),
                    dict(count=6, label="6m", step="month", stepmode="backward"),
                    dict(count=1, label="1y", step="year", stepmode="backward"),
                    dict(step="all")
                ])
            ),
            rangeslider=dict(visible=True),
            type="date"
        )
        weight_graph_html = fig_weight.to_html(full_html=False)

    if not df_bmi.empty:
        # 日付でソート（古い日付から新しい日付へ）
        df_bmi = df_bmi.sort_values(by='Date')
        fig_bmi = px.line(df_bmi, x='Date', y='BMI', title='BMIの推移')
        fig_bmi.update_xaxes(
            rangeselector=dict(
                buttons=list([
                    dict(count=7, label="1w", step="day", stepmode="backward"),
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(count=3, label="3m", step="month", stepmode="backward"),
                    dict(count=6, label="6m", step="month", stepmode="backward"),
                    dict(count=1, label="1y", step="year", stepmode="backward"),
                    dict(step="all")
                ])
            ),
            rangeslider=dict(visible=True),
            type="date"
        )
        bmi_graph_html = fig_bmi.to_html(full_html=False)

    return render_template('dashboard.html', title='Dashboard', records=records,
                           weight_graph_html=weight_graph_html,
                           bmi_graph_html=bmi_graph_html)

# 健康記録の追加
@app.route("/record/new", methods=['GET', 'POST'])
@login_required
def new_record():
    if request.method == 'POST':
        date_str = request.form['date']
        weight = float(request.form['weight'])
        height = float(request.form['height']) if request.form['height'] else None
        notes = request.form['notes']

        # 日付文字列をdatetimeオブジェクトに変換
        date = datetime.strptime(date_str, '%Y-%m-%d').date()

        record = HealthRecord(user_id=current_user.id, date=date,
                              weight=weight, height=height, notes=notes)
        record.calculate_bmi() # BMIを計算
        try:
            db.session.add(record)
            db.session.commit()
            flash('健康記録が追加されました！', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'記録の追加に失敗しました: {e}', 'danger')
            app.logger.error(f"Add record error: {e}") # ログ出力
    return render_template('create_record.html', title='New Record')

# 健康記録の編集
@app.route("/record/<int:record_id>/edit", methods=['GET', 'POST'])
@login_required
def edit_record(record_id):
    record = HealthRecord.query.get_or_404(record_id)
    if record.user_id != current_user.id:
        flash('この記録を編集する権限がありません。', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        record.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        record.weight = float(request.form['weight'])
        record.height = float(request.form['height']) if request.form['height'] else None
        record.notes = request.form['notes']
        record.calculate_bmi() # BMIを再計算
        try:
            db.session.commit()
            flash('健康記録が更新されました！', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'記録の更新に失敗しました: {e}', 'danger')
            app.logger.error(f"Edit record error: {e}") # ログ出力
    return render_template('edit_record.html', title='Edit Record', record=record)

# 健康記録の削除
@app.route("/record/<int:record_id>/delete", methods=['POST'])
@login_required
def delete_record(record_id):
    record = HealthRecord.query.get_or_404(record_id)
    if record.user_id != current_user.id:
        flash('この記録を削除する権限がありません。', 'danger')
        return redirect(url_for('dashboard'))
    try:
        db.session.delete(record)
        db.session.commit()
        flash('健康記録が削除されました！', 'success')
    except Exception as e:
        flash(f'記録の削除に失敗しました: {e}', 'danger')
        app.logger.error(f"Delete record error: {e}") # ログ出力
    return redirect(url_for('dashboard'))

# アプリケーション起動
if __name__ == '__main__':
    # ローカルで実行する場合のみdb.create_all()を呼ぶ
    # Renderではビルドコマンドで一度だけ実行するため、ここではコメントアウトしておく
    # with app.app_context():
    #     db.create_all()
     pass 