from flask import Flask, render_template, flash,request,url_for,logging,session,redirect,jsonify
from flaskext.mysql import MySQL
from wtforms import *
from passlib.hash import sha256_crypt
from functools import wraps
import secrets,os,requests

app=Flask(__name__)

#config mysql database
app.config['MYSQL_DATABASE_HOST']='localhost'
app.config['MYSQL_DATABASE_USER']='root'
app.config['MYSQL_DATABASE_PASSWORD']='toor'
app.config['MYSQL_DATABASE_DB']='akhil'
app.config['MYSQL_CURSORCLASS']='DictCursor'
#init mysql
mysql=MySQL()
mysql.init_app(app)

conn=mysql.connect()
db=conn.cursor()

goodreads_key=os.getenv('GOODREAD_KEY')


class RegisterForm(Form):
		"""docstring for RegisterForm"""
		name=StringField('Name',[validators.Length(min=5 ,max=40)])
		username=StringField('Username',[validators.Length(min=5 ,max=40)])
		password= PasswordField('Password',[
			validators.DataRequired(),
			validators.EqualTo('confirm',message="passwords don't match")])
     			
		confirm=PasswordField('Confirm Password')
#Home page
@app.route('/')
def index():
    return render_template('home.html')

#Registering the user
@app.route('/register',methods=['GET','POST'])
def register():
	form=RegisterForm(request.form)
	if request.method=='POST' and form.validate():
		name=form.name.data 
		username=form.username.data
		password=sha256_crypt.hash(str(form.password.data))

		#executing query
		db.execute('insert into login(name,username,password) values(%s, %s,%s)',(name,username,password))
		#commit to db
		conn.commit()
		#closing connection to execution
		db.close()
		conn.close()
		flash('You are now registered and can log in','success')
		return redirect(url_for('login'))
	return render_template('register.html', form=form)
#generating a secure key to encrypt the user password
s=secrets.token_hex(20)

#logging in the user 
@app.route('/login',methods=['GET','POST'])
def login():
	if request.method=='POST':
		#Get Form Fields
		username=request.form['username']
		password_candidate=request.form['password']
		cur=conn.cursor()
		cur.execute('select * from login where username=%s',[username])
			#Get stored hash
		try:
			if cur.fetchone()[0]:
				cur.execute('select password from login where username=%s',[username])
				for row in cur.fetchall():
					if sha256_crypt.verify(password_candidate,row[0]):
						session['logged_in']=True
						session['username']=username
						flash=('You are now logged in','success')
						return redirect(url_for('dashboard'))
					else:
						error='Invalid login'
						return render_template('login.html',error=error)
					#close connection
					cur.close()
		except TypeError:		
				error='Username not found'
				return render_template('login.html',error=error)
	return render_template('login.html')

#Check if user is logged in
def is_logged_in(f):
	@wraps(f)
	def wrap(*args,**kwargs):
		if 'logged_in' in session:
			return f(*args,**kwargs)
		else:
			flash('Unauthorized,Please login','danger')
			return redirect(url_for('login'))
	return wrap

#Dashboard
@app.route('/dashboard',methods=['GET','POST'])
@is_logged_in
def dashboard():
	if request.method=='POST':
		query=request.form["search"]
		query='%'+query+'%'
		query=query.lower().strip()
		cur=conn.cursor()
		#querying database using wildcard
		cur.execute("select * from booklog where concat_ws('',isbn,title,author) like %s limit 100",(query))
		results=cur.fetchall()
		return render_template('dashboard.html',results=results)
		cur.close()
	return render_template('dashboard.html')

#Article Form class
class ArticleForm(Form):
	title=StringField('Title',[validators.length(min=5,max=60)])
	body=StringField('Title',[validators.length(min=30)])

@app.route('/review/<string:isbn>',methods=['GET','POST'])
@is_logged_in
def review(isbn):
	"""lists details about a single book"""
	cur=conn.cursor()
	cur.execute("select * from booklog where isbn=%s",(isbn))
	if request.method=='GET' and cur.rowcount != 0:
		good_reads,isbn = query_goodreads(isbn)
		message=str(isbn)
		return render_template('review.html',message=message,result=cur.fetchone(),good_reads=good_reads)
	form=ArticleForm(request.form)
	if request.method=="POST" and form.validate():
		author=session['username']
		title=request.form["title"]
		body=form.body.data
		rating=request.form['rating']
		good_reads,get=query_goodreads(isbn)
		isbn=get
		#user_id=cur.execute('select id from review where author=%s',(author))
		check=cur.execute('select author,isbn from review where author=%s and isbn=%s',(author,isbn))
		if cur.rowcount==0:
			cur.execute('insert into review(title,body,author,rating,isbn) values(%s,%s,%s,%s,%s)',(title,body,author,rating,isbn))
				#commiting to database
			conn.commit()
			flash('Review Created','success')
				#closing connection
			cur.close()
			return redirect(url_for('dashboard'))
		else:
			return render_template('error.html',message="Your review has been recorded and can't re-submit")
	else:
		return render_template('error.html',message='Wrong name try again')
	return render_template('review.html')
#good reads api
def query_goodreads(isbn):
	isbn=str(isbn)
	if len(isbn)<10:
		add=10-len(isbn)
		for i in range(add):
			isbn='0'+isbn
	if len(isbn)==10:
	    res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key":goodreads_key, "isbns":str(isbn)})
	    k = res.json()
	    goodreads_avg_rating=k['books'][0]['average_rating']
	    return goodreads_avg_rating,isbn
#api call
@app.route('/api/<string:isbn>')
def api(isbn):
    key =  goodreads_key
    res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key":key, "isbns": str(isbn)})
    res = res.json()
    isbn = str(isbn)
    row = db.execute('select * from booklog where isbn = %s' ,(isbn))
    if res is None or row is None:
        return jsonify({'error' : 'isbn not valid'})
    else:     
	    review_count = res['books'][0]['work_ratings_count']
	    average_score= res['books'][0]['average_rating']
	    return render_template('api.html',row=db.fetchone(), review_count=review_count, average_score=average_score)
#review the user articles 
@app.route('/article')
@is_logged_in
def article():
	author=session['username']
	db=conn.cursor()
	db.execute('select title,body,rating from review where author=%s',(author))
	if db.rowcount==0:
		return render_template('error.html',message='You made no reviews')
	data=db.fetchall()
	db.close()
	return render_template('article.html',data=data,message='Your Reviews')

#logout 
@app.route('/logout')
def logout():
	session.clear()
	flash('You are now logged out','success')
	return redirect(url_for('login'))

if __name__ == '__main__':
	app.secret_key=s
	app.debug=True
	app.run(host='localhost',port=5012)