# -*- coding: utf-8 -*-
from ez_setup import use_setuptools
use_setuptools()

from setuptools import setup


setup(
    name='mailman2twitter',
    version=__import__('mailman2twitter').get_version(),
    url='https://github.com/fgallina/mailman2twitter',
    author='Fabián Ezequiel Gallina',
    author_email='galli.87@gmail.com',
    description=('A dirty hack to push new mailman threads to twitter.'),
    entry_points={
        'console_scripts': [
            'mailman2twitter = mailman2twitter:main'
        ]
    },
    license='GPLv3+',
    packages=['mailman2twitter'],
    requires=[
        'beautifulsoup4(==4.3.2)',
        'python_twitter(==1.3.1)',
        'requests(==2.2.1)'
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Natural Language :: English'
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Topic :: Artistic Software',
        'Topic :: Utilities',
    ],
)
