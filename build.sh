cd ~/code/wa7pge-flask
source venv/bin/activate
python -m pip install -r requirements.txt
python sitebuilder.py build
#cp _redirects build/_redirects
npx -y pagefind --site build
