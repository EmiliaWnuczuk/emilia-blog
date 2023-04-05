import datetime
import os
from flask import Flask, render_template, redirect, url_for, flash, abort, request
from flask_bootstrap import Bootstrap
from flask_ckeditor import CKEditor
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from forms import LoginForm, RegisterForm, CreatePostForm, CommentForm
from flask_gravatar import Gravatar
import smtplib

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")
ckeditor = CKEditor(app)
Bootstrap(app)

# CONNECT TO DB
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///blog.db")
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)

gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)

with app.app_context():

    class User(UserMixin, db.Model):
        __tablename__ = "users"
        id = db.Column(db.Integer, primary_key=True)
        email = db.Column(db.String(100), unique=True)
        password = db.Column(db.String(100))
        name = db.Column(db.String(100))
        posts = relationship("BlogPost", back_populates="author")
        comments = relationship("Comment", back_populates="comment_author")


    class BlogPost(db.Model):
        __tablename__ = "blog_posts"
        id = db.Column(db.Integer, primary_key=True)
        author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
        author = relationship("User", back_populates="posts")
        title = db.Column(db.String(250), unique=True, nullable=False)
        subtitle = db.Column(db.String(250), nullable=False)
        date = db.Column(db.String(250), nullable=False)
        body = db.Column(db.Text, nullable=False)
        img_url = db.Column(db.String(250), nullable=False)
        comments = relationship("Comment", back_populates="parent_post")

    class Comment(db.Model):
        __tablename__ = "comments"
        id = db.Column(db.Integer, primary_key=True)
        author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
        comment_author = relationship("User", back_populates="comments")
        post_id = db.Column(db.Integer, db.ForeignKey("blog_posts.id"))
        parent_post = relationship("BlogPost", back_populates="comments")
        text = db.Column(db.Text, nullable=False)

    db.create_all()

    # decorator function preventing unauthorized users to make new posts
    def admin_only(function_x):
        @wraps(function_x)
        def decorated_finction(*args, **kwargs):
            if current_user.id != 1:
                return abort(403)
            return function_x(*args, **kwargs)
        return decorated_finction

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.route('/')
    def get_all_posts():
        posts = BlogPost.query.all()
        return render_template("index.html", all_posts=posts, current_user=current_user)

    @app.route('/register', methods=["GET", "POST"])
    def register():
        form = RegisterForm()

        if form.validate_on_submit():

            if User.query.filter_by(email=form.email.data).first():
                flash("You've already signed up with that email, log in instead!")
                return redirect(url_for("login"))

            password = generate_password_hash(
                password=form.password.data,
                method="pbkdf2:sha256",
                salt_length=4
            )
            new_user = User(
                email=form.email.data,
                password=password,
                name=form.name.data,
            )
            db.session.add(new_user)
            db.session.commit()

            login_user(new_user)

            return redirect(url_for('get_all_posts'))

        return render_template("register.html", form=form, current_user=current_user)


    @app.route('/login', methods=["GET", "POST"])
    def login():
        form = LoginForm()
        if form.validate_on_submit():
            email = form.email.data
            password = form.password.data
            user = User.query.filter_by(email=email).first()
            if user:
                if check_password_hash(user.password, password):
                    login_user(user)
                    return redirect(url_for('get_all_posts'))
                else:
                    flash("Password incorrect, please try again")
                    return redirect(url_for('login'))
            else:
                flash("That email does not exist, please try again")
                return redirect(url_for('login'))
        return render_template("login.html", form=form, current_user=current_user)


    @app.route('/logout')
    def logout():
        logout_user()
        return redirect(url_for('get_all_posts'))


    @app.route("/post/<int:index>", methods=["GET", "POST"])
    def show_post(index):
        form = CommentForm()
        requested_post = None
        posts = BlogPost.query.all()
        comments = Comment.query.all()

        for post in posts:
            if post.id == index:
                requested_post = post

        if form.validate_on_submit():
            if not current_user.is_authenticated:
                flash("YOu need to login or register to comment")
                return redirect(url_for('login'))

            new_comment = Comment(
                text=form.comment.data,
                comment_author=current_user,
                parent_post=requested_post,
            )
            db.session.add(new_comment)
            db.session.commit()

        return render_template("post.html", post=requested_post, form=form, comments=comments, current_user=current_user)


    @app.route("/new-post", methods=["GET", "POST"])
    @admin_only
    def new_post():
        form = CreatePostForm()
        if form.validate_on_submit():
            today = datetime.datetime.now()
            new_blog = BlogPost(
                title=form.title.data,
                subtitle=form.subtitle.data,
                date=f"{today.strftime('%B %d, %Y')}",
                body=form.body.data,
                author=current_user,
                img_url=form.img_url.data,
            )
            db.session.add(new_blog)
            db.session.commit()
            return redirect(url_for('get_all_posts'))

        return render_template("make-post.html", form=form, current_user=current_user)


    @app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
    @admin_only
    def edit_post(post_id):
        post = BlogPost.query.get(post_id)
        edit_form = CreatePostForm(
            title=post.title,
            subtitle=post.subtitle,
            img_url=post.img_url,
            author=post.author,
            body=post.body
        )
        if edit_form.validate_on_submit():
            post.title = edit_form.title.data
            post.subtitle = edit_form.subtitle.data
            post.body = edit_form.body.data
            post.img_url = edit_form.img_url.data
            db.session.commit()
            return redirect(url_for('show_post', index=post_id))

        return render_template("make-post.html", form=edit_form, is_edit=True, current_user=current_user)

    @app.route("/delete/<int:post_id>")
    @admin_only
    def delete(post_id):
        post_to_delete = BlogPost.query.get(post_id)
        db.session.delete(post_to_delete)
        db.session.commit()
        return redirect(url_for("get_all_posts"))


    @app.route("/about")
    def about():
        return render_template("about.html", current_user=current_user)

    MY_EMAIL = "homisek@gmail.com"
    MY_PASSWORD = "tbvvcmuxastyulpr"

    @app.route("/contact", methods=["GET", "POST"])
    def contact():
        if request.method == "POST":
            data = request.form
            print(data["nam"])
            print(data["emai"])
            print(data["phon"])
            print(data["messag"])

            with smtplib.SMTP("smtp.gmail.com", port=587) as connection:
                connection.starttls()
                connection.login(user=MY_EMAIL, password=MY_PASSWORD)
                connection.sendmail(
                    from_addr=MY_EMAIL,
                    to_addrs="wnuczukem@gmail.com",
                    msg=f"New 'contact me' message\n\nFrom: {data['nam']}\nE-mail: {data['emai']}\nPhone: "
                        f"{data['phon']}\nMessage: {data['messag']}"
                )
            return render_template("contact.html", current_user=current_user, msg_sent=True)

        return render_template("contact.html", current_user=current_user, msg_sent=False)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)

