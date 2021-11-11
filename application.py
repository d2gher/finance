import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Get the user id
    user_id = session["user_id"]
    # Get the stocks that the user currently owns
    stocks_owned = db.execute("SELECT * FROM owned WHERE buyer_id=?", user_id)
    # Create a variable to save the total amount of cash the user has and set it to the pure cash of the user
    cash = db.execute("SELECT cash FROM users WHERE id=?", user_id)[0].get("cash")
    total = cash
    # Create a dict to save the price of each stock in
    prices = dict()
    # Loop through the stocks the user owns and add it to the dict with it's total price
    for stock in stocks_owned:
        prices[stock.get("symbol")] = lookup(stock.get("symbol"))
        # Get price in USD
        prices[stock.get("symbol")]["priceUSD"] = usd(prices[stock.get("symbol")]["price"]);
        shares_total = prices[stock.get("symbol")]["price"] * stock.get("shares_number")

        prices[stock.get("symbol")]["price"] = int(prices[stock.get("symbol")]["price"]);
        # Add the price of each stock to the total amount of cash the user has
        total = total + shares_total
        prices[stock.get("symbol")]["total"] = usd(shares_total)


    cash = usd(cash)
    total = usd(total)
    return render_template("index.html", stocks_owned=stocks_owned, prices=prices, total=total, cash=cash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        # Get the purchase details from the request's body
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        try:
            shares = int(shares)
        except:
            return apology("Please use a number")

        if shares < 1:
            return apology("Please use a positive number")

        # Look up the stock price
        results = lookup(symbol)
        if results is None:
            return apology("Please use a valid stock symbol")

        # Get the user id from the cookies
        user_id = session["user_id"]

        # Get how much money the user has
        cash = db.execute("SELECT cash FROM users WHERE id=?", user_id)[0]
        cash = cash["cash"]

        stock_name = results["name"]
        price = results["price"]
        # Calculate the shares cost
        shares_cost = int(price) * shares

        # If user doesn't have enough money to complete the transaction
        if cash < shares_cost:
            return apology("You don't have enough money")

        # Take the amount of money from the user's account
        db.execute("UPDATE users SET cash=? WHERE id=?", cash - shares_cost, user_id)
        # Add the transaction to the purchase table in the database
        db.execute("INSERT INTO purchase (buyer_id, stock_name, price, shares_number, symbol) VALUES (?, ?, ?, ?, ?)",
                   user_id, stock_name, shares_cost, shares, symbol)

        # Find if the user owns any shares
        stock_exist = db.execute("SELECT 1 FROM owned WHERE buyer_id=? AND stock_name=?", user_id, stock_name)
        if stock_exist:
            db.execute("UPDATE owned SET shares_number = shares_number + ? WHERE buyer_id=? AND stock_name=?", shares, user_id, stock_name)
        else:
            db.execute("INSERT INTO owned (buyer_id, stock_name, shares_number, symbol) VALUES (?, ?, ?, ?)",
                       user_id, stock_name, shares, symbol)

        return redirect("/")

    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session["user_id"]
    # Get the user history, what he/she bought and sold
    buying_history = db.execute("SELECT * FROM purchase WHERE buyer_id=?", user_id)
    selling_history = db.execute("SELECT * FROM sold WHERE seller_id=?", user_id)
    # Save the information we got in one list
    transactions = selling_history + buying_history
    # Sort that list but the timestamp of each transaction
    transactions = sorted(transactions, key=lambda t: t['time'], reverse=True)

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        # Get the stock price through the API
        results = lookup(request.form.get("symbol"))

        # Check if the returned results are empty
        if results is None:
            return apology("Please use a valid stock symbol")

        results["price"] = usd(results.get("price"))
        print(results)
        # Render a new page with the results we got
        return render_template("quoted.html", results=results)

    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # Get the user info from the request's body
        username = request.form.get("username")
        passward = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Make sure the user wrote a username
        if not username:
            return apology("Username is required")
        # Make sure the username isn't already in the database
        username_exist = db.execute("SELECT 1 FROM users WHERE username=?", username)
        if username_exist:
            return apology("This user name is taken")

        # Make sure the user picked a passward
        if not passward:
            return apology("Passward is required")
        # Make sure the user wrote the same passward again
        if not passward == confirmation:
            return apology("Passwards don't match")

        # Save the username and password in our database
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, generate_password_hash(passward))

        # Log the user in by saving his id in the cookies
        user_id = db.execute("SELECT id FROM users WHERE username=?", username)
        session["user_id"] = user_id[0]["id"]

        # Redirect to the index page
        return redirect("/")

    return render_template("register.html")


@app.route("/cash", methods=["GET", "POST"])
@login_required
def Add_cash():
    """ Alow the user to add cash to their account """
    if request.method == "POST":
        user_id = session["user_id"]
        # Update the amount of cash the user has
        db.execute("UPDATE users SET cash = cash + ? WHERE id=?", request.form.get("cash"), user_id)

        return redirect("/")

    return render_template("cash.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # Get the user id from the cookies
    user_id = session["user_id"]
    purchase_history = db.execute("SELECT * FROM owned WHERE buyer_id=?", user_id)

    if request.method == "POST":
        # Get what and how much the user wants to sell
        symbol = request.form.get("symbol")
        shares_to_sell = int(request.form.get("shares"))

        # Throw an error if the user didn't choose
        if not symbol:
            return apology("Please select a symbol")
        if not shares_to_sell:
            return apology("please choose the number of shares you want to sell")

        # Check if the user owns that amount of that stock
        shares_owned = db.execute("SELECT 1 FROM owned WHERE symbol=? and shares_number>=?", symbol, shares_to_sell)
        # If not, through an error
        if not shares_owned:
            return apology("Sorry you can't sell what you don't own")

        # Loop up the stock's current price
        stock = lookup(symbol)
        share_price = int(stock.get("price"))
        stock_name = stock.get("name")

        # Calculate the price of the shares the user wants to sell
        total_price = shares_to_sell * share_price

        # Update to shares the user has to remove the shares he/she sold
        db.execute("UPDATE owned SET shares_number = shares_number - ? WHERE symbol=?", shares_to_sell, symbol)
        # See if the user sold all his/her shares, if so, delete from owned
        if db.execute("SELECT 1 FROM owned WHERE shares_number=? and buyer_id=? and symbol=?", 0, user_id, symbol):
            db.execute("DELETE FROM owned WHERE buyer_id=? and symbol=?", user_id, symbol)
        # Add the transaction to the user history
        db.execute("INSERT INTO sold (seller_id, symbol, stock_name, shares_number, price) VALUES (?, ?, ?, ?, ?)",
                   user_id, symbol, stock_name, shares_to_sell, total_price)
        # Add the cash the user got to his account
        db.execute("UPDATE users SET cash = cash + ? WHERE id=?", total_price, user_id)

        return redirect("/")

    return render_template("sell.html", purchase_history=purchase_history)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
