from flask import Flask, render_template, redirect, url_for, request, flash
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy
# from flask_wtf import FlaskForm
# from wtforms import StringField, SubmitField
# from wtforms.validators import DataRequired, URL
from flask_ckeditor import CKEditor, CKEditorField
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import relationship
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
from flask_gravatar import Gravatar
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm
from functools import wraps
from flask import abort
import smtplib
import os
import datetime

EMAIL = os.environ["EMAIL"]
PASSWORD = os.environ["PASSWORD"]

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ["SECRET_KEY"]
ckeditor = CKEditor(app)
Bootstrap(app)

##CONNECT TO DB
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL",  "sqlite:///blog.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Contains all the code that lets the Flask application work alongside Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

# gravatar usage
gravatar = Gravatar(app, size=100, rating='g', default='retro', force_default=False, force_lower=False, use_ssl=False, base_url=None)

##CONFIGURE TABLE
class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id = db.Column(db.Integer, primary_key=True)

    # Create Foreign Key, "user.id" the users refers to the tablename of User.
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    # References the User object, the "posts" refers to the posts property in the User class.
    author = relationship("User", back_populates="posts")

    # References the Comment object, the parent_post refers to the parent_post property in the Comment class.
    comments = relationship("Comment", back_populates="parent_post")

    title = db.Column(db.String(250), unique=True, nullable=False)
    subtitle = db.Column(db.String(250), nullable=False)
    date = db.Column(db.String(250), nullable=False)
    body = db.Column(db.Text, nullable=False)
    img_url = db.Column(db.String(250), nullable=False)

##CREATE TABLE IN DB
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(1000))

    # This represents the many relationship between an author and the ability to have many posts.
    posts = relationship("BlogPost", back_populates="author")

    # This represents the relationship the relationship between a user and the ability to have many comments.
    comments = relationship("Comment", back_populates="comment_author")

class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    # Create Foreign Key, "user.id" the users refers to the tablename of User.
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    # References the User object, the "comments" refers to the comments property in the User class.
    comment_author = relationship("User", back_populates="comments")

    # Foreign Key "blog_posts.id", blog_posts refers to the BlogPost DB table name.
    post_id = db.Column(db.Integer, db.ForeignKey("blog_posts.id"))
    # References the post object, the comments refers to the fact a blog post can have many comments on it.
    parent_post = relationship("BlogPost", back_populates="comments")

    text = db.Column(db.Text, nullable=False)

# Creates all the tables in the database
db.create_all()

# ------------------------- Login Decorators and functions ---------------------

@login_manager.user_loader
def load_user(user_id):
    '''Represents a callback function to reload the user object stored at the users ID'''
    return User.query.get(int(user_id))

def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # If the person isn't logged in then redirect them to login
        if not current_user.is_authenticated:
            return redirect(url_for('login', next=request.url))
        # If id doesn't represent an admin id then give them a 403
        elif current_user.id != 1:
            return abort(403)
        # else continue with the route function
        return f(*args, **kwargs)
    return decorated_function

# ------------------------------------- Base Website Routes --------------------------

# Renders the home page
@app.route('/')
def get_all_posts():
    '''Renders the home page and previews all posts.'''
    posts = BlogPost.query.all()
    return render_template("index.html", all_posts=posts, logged_in=current_user)



@app.route("/about")
def about():
    '''Renders the page about the site.'''
    return render_template("about.html", logged_in=current_user)


@app.route('/contact', methods=["GET", "POST"])
def contact():
    '''Represents the contact form needed to contact the site. '''
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        phone_number = request.form["phone"]
        message = request.form["message"]
        send_emails(name, email, phone_number, message)
        return render_template("contact.html", msg_sent=True, logged_in=current_user)
    return render_template("contact.html", msg_sent=False, logged_in=current_user)

def send_emails(name, email, phone_number, message):
    '''Sends an email with the user inputted form data to the website's email'''
    with smtplib.SMTP("smtp.gmail.com", port=587) as connection:
        email_message=f"Name: {name}, EmailAddress: {email}, PhoneNumber: {phone_number}\n{message}"
        connection.starttls()
        connection.login(user=EMAIL, password=PASSWORD)
        connection.sendmail(from_addr=EMAIL,
                            to_addrs=EMAIL,
                            msg=email_message)

@app.route("/post/<int:index>", methods=["GET", "POST"])
def show_post(index):
    '''This will render the appropriate post from the database using the primary_key id'''
    requested_post = BlogPost.query.get(index)
    comment_form = CommentForm()
    if comment_form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You need to login or register before commenting.")
            return redirect(url_for("login"))

        new_comment = Comment(
            text=request.form['comment_body'],
            comment_author=current_user,
            parent_post=requested_post
        )
        db.session.add(new_comment)
        db.session.commit()

    return render_template("post.html", post=requested_post, logged_in=current_user, form=comment_form)

# ------------------------------ Registration and Login Section ---------------------------

@app.route('/register', methods=["GET", "POST"])
def register():
    register_form = RegisterForm()
    if register_form.validate():
        email = request.form['email']
        check_user = User.query.filter_by(email=email).first()

        if not check_user:
            password_to_hash = request.form['password']
            hashed_password = generate_password_hash(
                password=password_to_hash,
                method='pbkdf2:sha256',
                salt_length=8
            )

            new_user = User(
                email=request.form['email'],
                password=hashed_password,
                name = request.form['name']
            )

            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for("get_all_posts"))

        else:
            flash("You've already signed up with that email, please login.")
            return redirect(url_for("login"))

    return render_template("register.html", form=register_form, logged_in=current_user)


@app.route('/login', methods=["GET", "POST"])
def login():
    error = None
    login_form = LoginForm()
    if login_form.validate_on_submit():
        # Query the DB using the unique identifier email to grab the user data.
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user != None:

            if check_password_hash(pwhash=user.password, password=password):
                login_user(user)
                return redirect(url_for("get_all_posts"))

            else:
                # password check returned false
                flash("Incorrect password, try again.")
                return redirect(url_for("login"))

        else:
            # the user registered with that email doesn't exist.
            flash("That email doesn't exist, please try again.")
            return redirect(url_for("login"))

    return render_template("login.html", form=login_form, logged_in=current_user)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


# -------------------CRUD Operations with Posts---------------------------

@app.route('/new-post', methods=["GET", "POST"])
#Marked with decorator
@admin_only
def new_post():
    '''Render a page that allows a user to create a new post.'''
    form = CreatePostForm()

    if form.validate_on_submit():
        # grab the data from the post and add it into the database
        posted_date = datetime.datetime.now()
        created_post = BlogPost(
        title=request.form['title'],
        subtitle = request.form['subtitle'],
        author_id = current_user.id,
        date = posted_date.strftime("%B %d, %Y"),
        img_url = request.form['img_url'],
        body = request.form.get('body'),
        )

        # commit the created post into the database.
        db.session.add(created_post)
        db.session.commit()

        # redirect the user to come back to the home page.
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form, logged_in=current_user)

@app.route("/edit-post/<int:index>", methods=["GET", "POST"])
#Marked with decorator
@admin_only
def edit_post(index):
    '''Renders the new-post html, however containing the previous data on the post autofilled into the post'''
    # get the data from the database to autofill the data in the form
    post_to_edit = BlogPost.query.get(index)

    edit_form = CreatePostForm(
        title=post_to_edit.title,
        subtitle=post_to_edit.subtitle,
        date=post_to_edit.date,
        img_url=post_to_edit.img_url,
        body=post_to_edit.body,
    )

    if edit_form.validate_on_submit():
        # grab the data from the post and add it into the database
        posted_date = datetime.datetime.now()
        post_to_edit.title = request.form['title']
        post_to_edit.subtitle = request.form['subtitle']
        post_to_edit.date = posted_date.strftime("%B %d, %Y")
        post_to_edit.img_url = request.form['img_url']
        post_to_edit.body = request.form.get('body')


        # commit the created post into the database.
        db.session.commit()

        # redirect the user to come back to the home page.
        return redirect(url_for("get_all_posts"))

    return render_template("make-post.html", form=edit_form, is_edit=True, logged_in=current_user)

@app.route("/delete/<int:index>")
#Marked with decorator
@admin_only
def delete_post(index):
    post_to_delete = BlogPost.query.get(index)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


if __name__ == "__main__":
    app.run(debug=True)
    # app.run(host='0.0.0.0', port=5000)