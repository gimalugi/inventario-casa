# Regression tests

Install the application requirements in an isolated Python environment, then run:

```sh
python -m unittest discover -s tests -v
node tests/test_pagination.cjs
```

Tests create temporary databases and images. They never import the production
application or access `/data` or `/media`. The Python tests need Flask and Pillow;
the JavaScript test uses only Node.js built-ins and needs no npm dependencies.

I test usano soltanto database e immagini temporanei e non accedono ai dati reali.
