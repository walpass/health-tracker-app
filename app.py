import os
from datetime import datetime, date
from flask import Flask, render_template, url_for, flash, redirect, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
import plotly.express as px
import pandas as pd
import numpy as np
from flask_migrate import Migrate
import logging

# ロギング設定 (追加)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# forms.py から必要なフォームをインポート
from forms import RegistrationForm, LoginForm, GroupForm, AddMemberForm

# Flaskアプリケーションの初期化
app = Flask(__name__)

# Jinja2フィルター
@app.template_filter('date')
def format_date(value, format="%Y-%m-%d"):
    """日付をフォーマットするJinja2フィルター"""
    if isinstance(value, datetime):
        return value.strftime(format)
    elif isinstance(value, date):
        return value.strftime(format)
    return value

# データベースURIを環境変数から取得、なければSQLiteを使用
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///site.db')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'b2686229b2e901ce32cde29c08627e93e6fb28e2ed732a7b')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_ENABLED'] = True

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

migrate = Migrate(app, db)

# --- Group モデル ---
class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    leader_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    # Group.leader から User オブジェクトにアクセス
    # User.leading_group から Group オブジェクトにアクセス (リーダーである場合)
    leader = db.relationship(
        'User',
        backref='leading_group',
        lazy=True,
        primaryjoin="Group.leader_id == User.id",
        post_update=True # 循環参照を避けるための設定
    )
    # Group.members から User オブジェクトのリストにアクセス
    # User.group から Group オブジェクトにアクセス (メンバーである場合)
    members = db.relationship(
        'User',
        backref='group',
        lazy=True,
        foreign_keys='User.group_id'
    )

    def __repr__(self):
        return f'<Group {self.name}>'

# --- User モデル ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    gender = db.Column(db.String(10))
    height = db.Column(db.Float, nullable=True)
    birth_date = db.Column(db.Date)
    health_data = db.relationship('HealthRecord', backref='user', lazy=True)

    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True)
    role = db.Column(db.String(20), default='member', nullable=False) # 'member', 'leader', 'admin'

    target_weight = db.Column(db.Float, nullable=True)
    target_bmi = db.Column(db.Float, nullable=True)

    def __repr__(self):
        return f'<User {self.username}>'

# --- 健康記録モデル ---
class HealthRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    weight = db.Column(db.Float, nullable=False)
    height = db.Column(db.Float, nullable=True)
    bmi = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"HealthRecord('{self.weight}', '{self.date}')"

    def calculate_bmi(self):
        if self.weight and self.height:
            height_m = self.height / 100
            self.bmi = round(self.weight / (height_m ** 2), 2)
        else:
            self.bmi = None

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ルート定義 ---

@app.route("/")
@app.route("/home")
def home():
    return render_template('home.html', title='Home')

@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = RegistrationForm()
    if form.validate_on_submit():
        existing_user_username = User.query.filter_by(username=form.username.data).first()
        existing_user_email = User.query.filter_by(email=form.email.data).first()

        if existing_user_username:
            flash('そのユーザー名はすでに使われています。別のユーザー名を選んでください。', 'danger')
            return render_template('register.html', title='Register', form=form)
        if existing_user_email:
            flash('そのメールアドレスはすでに使われています。別のメールアドレスを選んでください。', 'danger')
            return render_template('register.html', title='Register', form=form)

        hashed_password = generate_password_hash(form.password.data, method='pbkdf2:sha256')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password)
        try:
            db.session.add(user)
            db.session.commit()
            flash('アカウントが作成されました！ログインしてください。', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'登録に失敗しました: {e}', 'danger')
            db.session.rollback()
            app.logger.error(f"Registration error: {e}")
    return render_template('register.html', title='Register', form=form)

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            flash('ログインに成功しました！', 'success')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('ログインに失敗しました。メールアドレスまたはパスワードを確認してください。', 'danger')
    return render_template('login.html', title='ログイン', form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash('ログアウトしました。', 'info')
    return redirect(url_for('home'))

def generate_weight_graph(records, target_weight=None):
    if not records or len(records) < 2:
        return None

    df = pd.DataFrame([(r.date, r.weight) for r in records], columns=['Date', 'Weight'])
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values('Date')

    fig = px.line(df, x='Date', y='Weight', title='体重の推移')
    fig.update_xaxes(title_text='日付', tickformat="%Y-%m-%d")
    fig.update_yaxes(title_text='体重 (kg)')

    if target_weight is not None and target_weight > 0:
        fig.add_hline(y=target_weight, line_dash="dot", annotation_text=f"目標体重: {target_weight}kg", annotation_position="bottom right", line_color="green")

    return fig.to_html(full_html=False)

def generate_bmi_graph(records, target_bmi=None):
    if not records or len(records) < 2:
        return None

    df = pd.DataFrame([(r.date, r.bmi) for r in records if r.bmi is not None], columns=['Date', 'BMI'])
    if df.empty or len(df) < 2:
        return None

    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values('Date')

    fig = px.line(df, x='Date', y='BMI', title='BMIの推移')
    fig.update_xaxes(title_text='日付', tickformat="%Y-%m-%d")
    fig.update_yaxes(title_text='BMI')

    if target_bmi is not None and target_bmi > 0:
        fig.add_hline(y=target_bmi, line_dash="dot", annotation_text=f"目標BMI: {target_bmi}", annotation_position="bottom right", line_color="green")

    return fig.to_html(full_html=False)

# ダッシュボード
@app.route("/dashboard")
@login_required
def dashboard():
    records = HealthRecord.query.filter_by(user_id=current_user.id).order_by(HealthRecord.date.desc()).all()

    user_target_weight = current_user.target_weight if current_user.target_weight else None
    user_target_bmi = None
    if user_target_weight is not None and current_user.height is not None and current_user.height > 0:
        height_m = current_user.height / 100
        calculated_bmi = round(user_target_weight / (height_m * height_m), 2)
        if 10 <= calculated_bmi <= 40:
            user_target_bmi = calculated_bmi
        else:
            user_target_bmi = None

    weight_graph_html = generate_weight_graph(records, target_weight=user_target_weight)
    bmi_graph_html = generate_bmi_graph(records, target_bmi=user_target_bmi)

    # リーダーの場合、グループメンバーを取得
    group_members = []
    leading_group_name = None
    if current_user.role == 'leader' and current_user.group_id:
        group = Group.query.get(current_user.group_id)
        if group:
            leading_group_name = group.name
            # 自分のグループのメンバーを取得（自分自身は除く）
            group_members = User.query.filter_by(group_id=current_user.group_id).filter(User.id != current_user.id).all()

    return render_template('dashboard.html', title='Dashboard', records=records,
                            weight_graph_html=weight_graph_html,
                            bmi_graph_html=bmi_graph_html,
                            current_user=current_user,
                            group_members=group_members,
                            leading_group_name=leading_group_name)

# プロフィール/目標設定ページ
@app.route("/profile", methods=['GET', 'POST'])
@login_required
def profile():
    user = current_user
    if request.method == 'POST':
        try:
            # ユーザー名がフォームから送られてきていれば更新
            if 'username' in request.form:
                user.username = request.form['username']

            # Noneを許容するため、空文字列の場合はNoneに変換
            user.target_weight = float(request.form['target_weight']) if request.form['target_weight'] else None
            user.height = float(request.form['height']) if request.form['height'] else None

            # フォームに性別、生年月日を追加した場合の処理 (未実装の場合でもエラーにならないように)
            # if 'gender' in request.form:
            #     user.gender = request.form['gender']
            # if 'birth_date' in request.form and request.form['birth_date']:
            #     user.birth_date = datetime.strptime(request.form['birth_date'], '%Y-%m-%d').date()

            db.session.commit()
            flash('プロフィールが更新されました！', 'success')
            return redirect(url_for('profile'))
        except ValueError:
            flash('入力には有効な数値を入力してください。', 'danger')
            db.session.rollback()
        except Exception as e:
            flash(f'更新に失敗しました: {e}', 'danger')
            db.session.rollback()
            app.logger.error(f"Profile update error: {e}")
    return render_template('profile.html', title='プロフィール', user=user)

# グループ作成ページ
@app.route("/group/new", methods=['GET', 'POST'])
@login_required
def new_group():
    # 既にグループリーダーである場合はグループ作成を制限
    if current_user.role == 'leader' and current_user.group_id:
        flash('あなたは既にグループリーダーです。新しいグループを作成することはできません。', 'warning')
        return redirect(url_for('dashboard'))

    form = GroupForm()
    if form.validate_on_submit():
        # グループ名が既に存在するかチェック
        existing_group = Group.query.filter_by(name=form.name.data).first()
        if existing_group:
            flash('そのグループ名はすでに使われています。別のグループ名を選んでください。', 'danger')
            return render_template('create_group.html', title='新しいグループを作成', form=form)

        group = Group(name=form.name.data, leader_id=current_user.id)
        try:
            db.session.add(group)
            db.session.commit()
            # グループ作成後、現在のユーザーをそのグループのリーダーに設定
            current_user.group_id = group.id
            current_user.role = 'leader'
            db.session.commit()
            flash(f'グループ "{group.name}" が作成されました！', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'グループ作成に失敗しました: {e}', 'danger')
            db.session.rollback()
            app.logger.error(f"Group creation error: {e}")
    return render_template('create_group.html', title='新しいグループを作成', form=form)

# 健康記録の追加
@app.route("/record/new", methods=['GET', 'POST'])
@login_required
def new_record():
    if request.method == 'POST':
        try:
            date_str = request.form['date']
            weight = float(request.form['weight'])
            height = float(request.form['height']) if request.form['height'] else None
            notes = request.form.get('notes', None)

            # 'date' との変数名衝突を避けるため 'record_date' を使用
            record_date = datetime.strptime(date_str, '%Y-%m-%d').date()

            record = HealthRecord(user_id=current_user.id, date=record_date,
                                    weight=weight, height=height, notes=notes)
            record.calculate_bmi() # BMIを計算

            db.session.add(record)
            db.session.commit()
            flash('健康記録が追加されました！', 'success')
            return redirect(url_for('dashboard'))
        except ValueError:
            flash('体重と身長には有効な数値を入力してください。', 'danger')
            db.session.rollback()
        except Exception as e:
            flash(f'記録の追加に失敗しました: {e}', 'danger')
            app.logger.error(f"Add record error: {e}")
            db.session.rollback()

    today = date.today().isoformat()
    # ユーザーの身長をデフォルト値として表示
    default_height = current_user.height if current_user.height else ''
    return render_template('create_record.html', title='新しい記録', today=today, default_height=default_height)

# 健康記録の編集
@app.route("/record/<int:record_id>/edit", methods=['GET', 'POST'])
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
            record.height = float(request.form['height']) if request.form['height'] else None
            record.notes = request.form.get('notes', None)
            record.calculate_bmi() # BMIを再計算

            db.session.commit()
            flash('健康記録が更新されました！', 'success')
            return redirect(url_for('dashboard'))
        except ValueError:
            flash('体重と身長には有効な数値を入力してください。', 'danger')
            db.session.rollback()
        except Exception as e:
            flash(f'記録の更新に失敗しました: {e}', 'danger')
            db.session.rollback()
            app.logger.error(f"Edit record error: {e}")
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
        app.logger.error(f"Delete record error: {e}")
        db.session.rollback()
    return redirect(url_for('dashboard'))

# メンバー招待ページ (リーダーのみ)
@app.route("/group/add_member", methods=['GET', 'POST'])
@login_required
def add_member_to_group():
    # リーダーのみがアクセスできるように制限
    if current_user.role != 'leader' or not current_user.group_id:
        flash('この機能を利用するにはグループリーダーである必要があります。', 'danger')
        return redirect(url_for('dashboard'))

    form = AddMemberForm()
    users_found = [] # 検索結果を格納するリスト

    # 検索フォームがサブミットされた場合
    if form.validate_on_submit() and form.search_query.data: # search_queryがある場合のみ処理
        search_term = form.search_query.data
        # ユーザー名またはメールアドレスで検索
        users_found = User.query.filter(
            (User.username.like(f'%{search_term}%')) |
            (User.email.like(f'%{search_term}%'))
        ).all()

        # 検索結果から現在のリーダー自身と既にグループに所属しているメンバーを除外
        users_found = [
            u for u in users_found
            if u.id != current_user.id and (u.group_id is None or u.group_id != current_user.group_id)
        ]
        if not users_found:
            flash('指定された条件に一致するユーザーは見つかりませんでした。', 'info')

    # POSTリクエストで招待アクションが送られてきた場合
    # form.validate_on_submit() と同時に 'invite_user_id' が来ることはない（別々のサブミット）ので、分けて処理
    if request.method == 'POST' and 'invite_user_id' in request.form:
        invited_user_id = request.form.get('invite_user_id', type=int)
        user_to_invite = User.query.get(invited_user_id)

        if user_to_invite:
            # 招待されるユーザーが既にグループに所属していないか、または現在のリーダーのグループとは別のグループに所属しているかを確認
            if user_to_invite.group_id is None or user_to_invite.group_id != current_user.group_id:
                try:
                    user_to_invite.group_id = current_user.group_id
                    user_to_invite.role = 'member' # 招待されたユーザーはメンバーロール
                    db.session.commit()
                    flash(f'ユーザー "{user_to_invite.username}" をグループに招待しました。', 'success')
                except Exception as e:
                    flash(f'メンバーの追加に失敗しました: {e}', 'danger')
                    db.session.rollback()
                    app.logger.error(f"Add member error: {e}")
            else:
                flash('招待するユーザーは既にこのグループに所属しています。', 'warning')
        else:
            flash('招待するユーザーが見つかりませんでした。', 'warning')
        return redirect(url_for('add_member_to_group')) # 処理後、同じページにリダイレクト

    return render_template('add_member_to_group.html',
                            title='メンバーを招待',
                            form=form,
                            users_found=users_found)

# 【追加】メンバーの削除機能 (リーダーのみ)
@app.route("/group/remove_member", methods=['POST'])
@login_required
def remove_member_from_group():
    # リーダーのみがアクセスできるように制限
    if current_user.role != 'leader' or not current_user.group_id:
        flash('この機能を利用するにはグループリーダーである必要があります。', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        member_id_to_remove = request.form.get('member_id_to_remove', type=int)
        member_to_remove = User.query.get(member_id_to_remove)

        if member_to_remove:
            # 削除対象が自分自身ではないか、かつ自分のグループのメンバーかを確認
            if member_to_remove.id == current_user.id:
                flash('自分自身をグループから削除することはできません。', 'warning')
            elif member_to_remove.group_id == current_user.group_id:
                try:
                    member_to_remove.group_id = None # グループから離脱
                    member_to_remove.role = 'member' # 役割をデフォルトの'member'に戻す (将来の再加入に備え)
                    db.session.commit()
                    flash(f'ユーザー "{member_to_remove.username}" をグループから削除しました。', 'success')
                except Exception as e:
                    flash(f'メンバーの削除に失敗しました: {e}', 'danger')
                    db.session.rollback()
                    app.logger.error(f"Remove member error: {e}")
            else:
                flash('指定されたユーザーはこのグループに所属していません。', 'warning')
        else:
            flash('削除するユーザーが見つかりませんでした。', 'warning')

    return redirect(url_for('add_member_to_group')) # メンバー管理ページにリダイレクト

# メンバーのダッシュボード表示 (リーダーのみ)
@app.route("/dashboard/<int:user_id>")
@login_required
def view_member_dashboard(user_id):
    # 現在のユーザーがリーダーであること、かつ、表示しようとしているユーザーが自分のグループのメンバーであることを確認
    if not current_user.is_authenticated or current_user.role != 'leader':
        flash('他のユーザーのダッシュボードを表示する権限がありません。', 'danger')
        return redirect(url_for('dashboard'))

    member = User.query.get_or_404(user_id)
    # メンバーが自分のグループに所属しているかチェック
    if member.group_id != current_user.group_id:
        flash('このユーザーはあなたのグループに所属していません。', 'danger')
        return redirect(url_for('dashboard'))

    records = HealthRecord.query.filter_by(user_id=member.id).order_by(HealthRecord.date.desc()).all()

    member_target_weight = member.target_weight if member.target_weight else None
    member_target_bmi = None
    if member_target_weight is not None and member.height is not None and member.height > 0:
        height_m = member.height / 100
        calculated_bmi = round(member_target_weight / (height_m * height_m), 2)
        if 10 <= calculated_bmi <= 40: # BMIの一般的な有効範囲を考慮
            member_target_bmi = calculated_bmi
        else:
            member_target_bmi = None

    weight_graph_html = generate_weight_graph(records, target_weight=member_target_weight)
    bmi_graph_html = generate_bmi_graph(records, target_bmi=member_target_bmi)

    return render_template('dashboard.html', title=f'{member.username} のダッシュボード', records=records,
                            weight_graph_html=weight_graph_html,
                            bmi_graph_html=bmi_graph_html,
                            current_user=member, # ここで current_user を member に上書きして、テンプレートが member のデータを表示するようにする
                            is_leader_view=True) # リーダー視点であることを示すフラグ

# 【新機能】リーダー向け：所属メンバーの最新記録一覧ページ
@app.route("/group/member_records")
@login_required
def view_group_member_records():
    # リーダーのみがアクセスできるように制限
    if current_user.role != 'leader' or not current_user.group_id:
        flash('この機能を利用するにはグループリーダーである必要があります。', 'danger')
        return redirect(url_for('dashboard'))

    group = Group.query.get(current_user.group_id)
    if not group:
        flash('所属するグループが見つかりません。', 'danger')
        return redirect(url_for('dashboard'))

    # リーダー自身は除外し、グループメンバーを取得
    members = User.query.filter_by(group_id=group.id).filter(User.id != current_user.id).all()

    # 各メンバーの最新の記録を取得
    member_latest_records = []
    for member in members:
        latest_record = HealthRecord.query.filter_by(user_id=member.id) \
                                        .order_by(HealthRecord.date.desc()) \
                                        .first() # 最新の記録を1件取得

        # 最新の記録が存在しないメンバーのために、デフォルト値を設定
        record_info = {
            'username': member.username,
            'latest_date': latest_record.date if latest_record else '記録なし',
            'weight': latest_record.weight if latest_record else 'N/A',
            'height': latest_record.height if latest_record else 'N/A',
            'bmi': latest_record.bmi if latest_record else 'N/A',
            'user_id': member.id # メンバーのダッシュボードへのリンク用
        }
        member_latest_records.append(record_info)

    # メンバーの名前でソートする (任意)
    member_latest_records.sort(key=lambda x: x['username'])

    return render_template('member_records.html',
                           title=f'{group.name} - メンバーの最新記録',
                           group_name=group.name,
                           member_latest_records=member_latest_records)


# アプリケーション起動
if __name__ == '__main__':
    # 開発中はdebug=Trueにすると、変更が自動で反映される (本番環境ではFalseにすること！)
    app.run(debug=True)