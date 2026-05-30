from flask import Flask
app = Flask(__name__)

@app.route('/')
def home():
    return {"status": "ok"}

@app.route('/api/get_messages')
def get_messages():
    return {"messages": []}

if __name__ == '__main__':
    import os
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))
