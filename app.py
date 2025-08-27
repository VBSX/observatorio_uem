from observatorio import create_app

app = create_app()

if __name__ == '__main__':
    # Em produção, use um servidor WSGI como Gunicorn ou uWSGI
    app.run()