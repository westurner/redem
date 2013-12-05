# Makefile for redem redditlog
#
# Usage:
# -------
# automated::
#
#	$ export REDDIT_USERNAME="<username>"
#	$ make backup_redditlog
#	# <enter password>
#	$ make [view]
#
# manual::
#
#	$ export REDDIT_USERNAME="<username>"
#	$ make backup_and_review	# fetch recent 1000 comments, submissions
#								# and view the generated json
#	# <enter password>
#	$ make merge				# merge all ./data/*data*.json files
#	$ make redditlog			# generate index.html and static files
#								# making separate commits for
#								# * static files
#								# * data (JSON, index.html)
#	$ make [view]  				# open generated index.html locally
#	$ make push_redditlog 		# git push generated page to origin gh-pages
#
#
# Files
# ------
#
# Three (3) JSON Files::
#
# 	JSONDL   	= ./data/redemdata.$(date).json  	# per-backup JSON
# 	JSONMERGED	= ./data/merged_json.json			# merged JSON
# 	JSONDATA 	= ../redditlog/data/redemdata.json	# redditlog JSON copy
#
# Redditlog static webpage (e.g. for a `gh-pages` GitHub pages branch)::
#
#	HTMLINDEX 	= index.html	# HTML (TOC, Comments, Submissions, URLs)
#	STATICFILES = static/		# Static JS, CSS for index.html
#	JSONDATA 	= data/redemdata.json				# redditlog JSON copy


_DATE:=			$(shell date +%Y%m%d-%H%M)
_JSONDL:=		./data/redemdata.$(_DATE).data.json
_JSONMERGED:=   ./data/merged_json.json

_PREFIX:=		../redditlog
_DATADIR:=		$(_PREFIX)/data
_HTMLDIR:=		$(_PREFIX)
_HTMLINDEX:=	$(_HTMLDIR)/index.html
_JSONDATA:=		$(_DATADIR)/redemdata.json
_STATICFILES:=	./redem/static/
_REDEM_BIN:=	redem

default: view

static:
	mkdir -p $(_DATADIR)
	mkdir -p $(_HTMLDIR)
	rsync -avpr $(_STATICFILES) $(_HTMLDIR)

backup:
	echo "backing up to $(_JSONDL)" && \
	$(_REDEM_BIN) --verbose \
		--backup \
		--json=$(_JSONDL) \
		--username=$(REDDIT_USERNAME) && \
	echo "Backed up to $(_JSONDL)"

backup_and_review: backup
	python -m json.tool $(_JSONDL) | less

merge:
	$(_REDEM_BIN) --verbose \
		--merge \
		--json=$(_JSONMERGED) \
		--username=$(REDDIT_USERNAME) \
		$(shell find . -type f -iname '*data*.json')

view_merged:
	python -m json.tool $(_JSONMERGED)

template:
	$(_REDEM_BIN) --verbose \
		--html \
		--json=$(_JSONDATA) \
		--html-output=$(_HTMLINDEX) \
		--username=$(REDDIT_USERNAME)

backup_and_template:
	$(_REDEM_BIN) --verbose \
		--backup \
		--html \
		--json=$(_JSONDATA) \
		--html-output=$(_HTMLINDEX) \
		--username=$(REDDIT_USERNAME)

clean_redditlog:
	cd $(_PREFIX) && \
	rm -rf $(_PREFIX)/* && \
	git checkout README.rst

commit_redditlog_static:
	cd $(_PREFIX) && \
	git add . && \
	git commit -m "Updated static files"

commit_redditlog:
	cd $(_PREFIX) && \
	git add . && \
	git commit -m "Updated redemdata.json and index.html"

push_redditlog:
	cd $(_PREFIX) && \
	git push origin gh-pages

cp_redemdata:
	cp $(_JSONMERGED) $(_JSONDATA)

redditlog:  static commit_redditlog_static \
			cp_redemdata \
			template \
			commit_redditlog

backup_redditlog: backup merge redditlog push_redditlog

clean:
	pyclean .

view:
	x-www-browser $(_HTMLINDEX)
