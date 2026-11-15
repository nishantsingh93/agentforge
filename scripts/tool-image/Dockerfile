FROM python@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
COPY lock_wheels.py /opt/agentforge/lock_wheels.py
RUN python -I -m pip --isolated download --index-url https://pypi.org/simple --only-binary=:all: --dest /opt/agentforge/wheels ruff==0.17.4 mypy==1.20.2 build==1.6.1 setuptools==80.10.2 \
    && python -I /opt/agentforge/lock_wheels.py \
    && python -I -m pip --isolated install --no-index --find-links=/opt/agentforge/wheels --require-hashes -r /opt/agentforge/tools.lock \
    && python -I -m pip check
