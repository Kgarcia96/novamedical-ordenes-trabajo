from setuptools import setup, find_packages

setup(
    name="novamedical-app",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "flask==2.2.5",
        "gunicorn==20.1.0", 
        "reportlab==3.6.12",
        "pillow==9.5.0"
    ]
)
