# Makefile para mala_pata_come_candela

PY=python3
PIP=pip
VENV=.venv
ACTIVATE=source $(VENV)/bin/activate

.PHONY: help venv install lock fmt lint run-request run-pipeline run-spotify

help:
	@echo "Targets disponibles:"
	@echo "  venv          - crea entorno virtual"
	@echo "  install       - instala dependencias en el venv"
	@echo "  lock          - congela versiones a requirements-freeze.txt"
	@echo "  run-request   - ejemplo: make run-request ARGS='"10 canciones de salsa dura clasica"'"
	@echo "  run-pipeline  - ejemplo: make run-pipeline IN=canciones.csv OUT=out/log_descargas.csv"
	@echo "  run-spotify   - ejemplo: make run-spotify ARGS='https://open.spotify.com/playlist/XXXX --count 20 --genre salsa'"

venv:
	$(PY) -m venv $(VENV)
	@echo "Activar con: source $(VENV)/bin/activate"

install: venv
	$(ACTIVATE) && $(PIP) install --upgrade pip
	$(ACTIVATE) && $(PIP) install -r requirements.txt

lock:
	$(ACTIVATE) && $(PIP) freeze > requirements-freeze.txt

run-request:
	$(ACTIVATE) && $(PY) request_to_csv.py $(ARGS)

run-pipeline:
	$(ACTIVATE) && mkdir -p out
	$(ACTIVATE) && $(PY) pipeline_music.py --input $(IN) --output $(OUT)

run-spotify:
	$(ACTIVATE) && $(PY) spotify_to_csv.py $(ARGS)
