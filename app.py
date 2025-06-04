import os
from flask import Flask, render_template, url_for, flash, redirect, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import plotly.graph_objects as go
import plotly.utils
import json
import numpy as np

app = Flask(__name__)
app.config['SECRET_KEY'] = 'b2686229b2e901ce32cde29c08627e93e6fb28e2ed732a7b' 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Jinja2カスタムフィルターの登録 (datetimeオブジェクトとdateオブジェクトの両方に対応)
@app.template_filter('date')
def format_date(value, format="%Y-%m-%d"):
    if isinstance(value, datetime):
        return value.strftime(format)
    elif isinstance(value, date):
        return value.strftime(format)
    return value

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# データベースモデル
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    target_weight = db.Column(db.Float, nullable=True) # 目標体重を追加
    target_bmi = db.Column(db.Float, nullable=True)    # 目標BMIを追加
    records = db.relationship('HealthRecord', backref='author', lazy=True)

class HealthRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    weight = db.Column(db.Float, nullable=False)
    height = db.Column(db.Float, nullable=False)
    bmi = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def calculate_bmi(self):
        if self.height > 0:
            height_m = self.height / 100
            self.bmi = round(self.weight / (height_m ** 2), 2)
        else:
            self.bmi = 0.0

    def __repr__(self):
        return f"HealthRecord('{self.date}', '{self.weight}', '{self.height}', '{self.bmi}')"

# ルート設定
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_password)
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('アカウントが作成されました！ログインしてください。', 'success')
            return redirect(url_for('login'))
        except:
            db.session.rollback()
            flash('ユーザー名が既に存在します。別のユーザー名をお試しください。', 'danger')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('ログインに成功しました！', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('ログインに失敗しました。ユーザー名またはパスワードが正しくありません。', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('ログアウトしました。', 'info')
    return redirect(url_for('home'))

# ダッシュボード
@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    today_date = date.today().isoformat()
    if request.method == 'POST':
        try:
            record_date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
            weight = float(request.form['weight'])
            height = float(request.form['height'])

            if weight <= 0 or height <= 0:
                flash('体重と身長は0より大きい値を入力してください。', 'danger')
                return redirect(url_for('dashboard'))

            new_record = HealthRecord(date=record_date, weight=weight, height=height, user_id=current_user.id)
            new_record.calculate_bmi()
            db.session.add(new_record)
            db.session.commit()
            flash('新しい記録が追加されました！', 'success')
            return redirect(url_for('dashboard'))
        except ValueError:
            flash('入力された値が不正です。体重と身長は数値で入力してください。', 'danger')
            db.session.rollback()
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'記録の追加中にエラーが発生しました: {e}', 'danger')
            db.session.rollback()
            return redirect(url_for('dashboard'))

    records = HealthRecord.query.filter_by(user_id=current_user.id).order_by(HealthRecord.date.asc()).all()

    # グラフデータ生成
    weight_chart_json = generate_weight_chart_json(records, current_user.target_weight)
    bmi_chart_json = generate_bmi_chart_json(records, current_user.target_bmi)

    return render_template('dashboard.html', 
                           today_date=today_date,
                           records=records,
                           weight_chart_json=weight_chart_json,
                           bmi_chart_json=bmi_chart_json,
                           current_user=current_user)

# 目標設定ページ
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        try:
            target_weight = float(request.form['target_weight'])
            target_bmi = float(request.form['target_bmi'])

            if target_weight <= 0:
                flash('目標体重は0より大きい値を入力してください。', 'danger')
                return redirect(url_for('profile'))
            
            if target_bmi <= 0:
                flash('目標BMIは0より大きい値を入力してください。', 'danger')
                return redirect(url_for('profile'))

            current_user.target_weight = target_weight
            current_user.target_bmi = target_bmi
            db.session.commit()
            flash('目標設定が更新されました！', 'success')
            return redirect(url_for('dashboard'))
        except ValueError:
            flash('入力された値が不正です。目標体重と目標BMIは数値で入力してください。', 'danger')
            db.session.rollback()
            return redirect(url_for('profile'))
        except Exception as e:
            flash(f'目標設定の更新中にエラーが発生しました: {e}', 'danger')
            db.session.rollback()
            return redirect(url_for('profile'))
            
    return render_template('profile.html')


# 記録の編集
@app.route('/edit_record/<int:record_id>', methods=['GET', 'POST'])
@login_required
def edit_record(record_id):
    record = HealthRecord.query.get_or_404(record_id)
    if record.user_id != current_user.id:
        flash('この記録を編集する権限がありません。', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        try:
            record.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
            record.weight = float(request.form['weight'])
            record.height = float(request.form['height'])

            if record.weight <= 0 or record.height <= 0:
                flash('体重と身長は0より大きい値を入力してください。', 'danger')
                return redirect(url_for('edit_record', record_id=record.id))

            record.calculate_bmi()
            db.session.commit()
            flash('記録が更新されました！', 'success')
            return redirect(url_for('dashboard'))
        except ValueError:
            flash('入力された値が不正です。体重と身長は数値で入力してください。', 'danger')
            db.session.rollback()
            return redirect(url_for('edit_record', record_id=record.id))
        except Exception as e:
            flash(f'記録の更新中にエラーが発生しました: {e}', 'danger')
            db.session.rollback()
            return redirect(url_for('edit_record', record_id=record.id))

    return render_template('edit_record.html', record=record)

# 記録の削除
@app.route('/delete_record/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    record = HealthRecord.query.get_or_404(record_id)
    if record.user_id != current_user.id:
        flash('この記録を削除する権限がありません。', 'danger')
        return redirect(url_for('dashboard'))
    try:
        db.session.delete(record)
        db.session.commit()
        flash('記録が削除されました。', 'success')
    except Exception as e:
        flash(f'記録の削除中にエラーが発生しました: {e}', 'danger')
        db.session.rollback()
    return redirect(url_for('dashboard'))

# グラフデータ生成関数
def generate_weight_chart_json(records, target_weight=None):
    if not records:
        return "{}"

    dates = [record.date.strftime('%Y-%m-%d') for record in records]
    weights = [record.weight for record in records] 

    # グラフのデータ定義
    data = [
        go.Scatter(x=dates, y=weights, mode='lines+markers', name='体重',
                   hovertemplate="日付=%{x}<br>体重(kg)=%{y:.1f}<extra></extra>")
    ]

    # 目標体重が設定されている場合、目標ラインを追加
    if target_weight is not None:
        data.append(
            go.Scatter(x=dates, y=[target_weight] * len(dates), mode='lines', name='目標体重',
                       line=dict(dash='dot', color='red'), # 点線で赤色
                       hovertemplate="目標体重(kg)=%{y:.1f}<extra></extra>")
        )

    fig_weight = go.Figure(
        data=data, # データに目標ラインも含む
        layout=go.Layout(
            title_text='体重の推移と目標', # タイトルも変更
            xaxis_title='日付',
            yaxis_title='体重(kg)',
            hovermode='x unified',
            showlegend=True, # 凡例表示
            legend=dict( # 凡例の位置調整
                x=0.01,
                y=0.99,
                xanchor='left',
                yanchor='top',
                bgcolor='rgba(255,255,255,0.8)',
                bordercolor='rgba(0,0,0,0.5)',
                borderwidth=1,
                font=dict(size=10)
            )
        )
    )
    return json.dumps(fig_weight.to_dict(), cls=plotly.utils.PlotlyJSONEncoder)

def generate_bmi_chart_json(records, target_bmi=None):
    if not records:
        return "{}"

    dates = [record.date.strftime('%Y-%m-%d') for record in records]
    bmis = [record.bmi for record in records]

    data = [ # dataリストで定義する
        go.Scatter(x=dates, y=bmis, mode='lines+markers', name='BMI',
                   hovertemplate="日付=%{x}<br>BMI=%{y:.2f}<extra></extra>")
    ]
    
    # 目標BMIが設定されている場合、目標ラインを追加
    if target_bmi is not None:
        data.append(
            go.Scatter(x=dates, y=[target_bmi] * len(dates), mode='lines', name='目標BMI',
                       line=dict(dash='dot', color='blue'), # 点線で青色
                       hovertemplate="目標BMI=%{y:.1f}<extra></extra>")
        )

    fig_bmi = go.Figure(
        data=data, # データに目標ラインも含む
        layout=go.Layout(
            title_text='BMIの推移と目標', # タイトルも変更
            xaxis_title='日付',
            yaxis_title='BMI',
            hovermode='x unified',
            showlegend=True, # 凡例表示
            legend=dict( # 凡例の位置調整
                x=0.01,
                y=0.99,
                xanchor='left',
                yanchor='top',
                bgcolor='rgba(255,255,255,0.8)',
                bordercolor='rgba(0,0,0,0.5)',
                borderwidth=1,
                font=dict(size=10)
            )
        )
    )
    return json.dumps(fig_bmi.to_dict(), cls=plotly.utils.PlotlyJSONEncoder)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=False) # debug=Falseに設定