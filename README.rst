===============
mailman2twitter
===============

A dirty hack to push new mailman threads to twitter.

Info
====

+ Author: Fabián Ezequiel Gallina
+ Contact: galli.87 at gmail dot com
+ Project homepage: https://github.com/fgallina/mailman2twitter/

Installation
============

Using pip should suffice::

    $ pip install git+https://github.com/fgallina/mailman2twitter.git#egg=mailman2twitter

Usage
=====

Once it's installed you can run `mailman2twitter` from the commandline.  Try
the `-h` switch for an extensive info on how to use and setup this script.

Here's a quick tutorial::

  $ # Create a basic configuration file
  $ mailman2twitter -c > ~/.config/mailman2twitter.conf
  $ # Edit the configuration file to meet your requirements
  $ emacs ~/.config/mailman2twitter.conf
  $ # Run it with no args and let the magic happen
  $ mailman2twitter

The recommended way to setup this script is using an hourly cron.

Configuration
=============

`mailman2twitter` will look for a configuration file at either of the
following locations::

  + ~/.config/mailman2twitter.conf
  + ~/.mailman2twitter.conf
  + /etc/mailman2twitter.conf

Issue `mailman2twitter -h` for details on configuration variables.

TODO
====
  + py3k
  + scheduled database cleanups
  + tests
