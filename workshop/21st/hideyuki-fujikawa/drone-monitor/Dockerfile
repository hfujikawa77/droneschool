FROM python:3.11-slim

LABEL permissions='{"ExposedPorts":{"9999/tcp":{}},"HostConfig":{"PortBindings":{"9999/tcp":[{"HostPort":""}]},"ExtraHosts":["host.docker.internal:host-gateway"]}}'
LABEL authors='[{"name": "Hideyuki Fujikawa", "email": "hfujikawa77@gmail.com"}]'
LABEL company='{"about": "", "name": "", "email": ""}'
LABEL type="other"
LABEL tags='["other"]'
LABEL readme=''
LABEL links='{}'
LABEL requirements=''

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# BlueOS のサブパス（/extensionv2/<sanitized_name>）。Swagger の Try it out を正しいパスへ向ける。
# sanitized_name は register_service の name "Drone Monitor" → "dronemonitor"。
# ローカル Docker でローカル確認する場合は `-e ROOT_PATH=` で空に上書きする。
ENV ROOT_PATH=/extensionv2/dronemonitor

EXPOSE 9999
# --no-access-log: Helper の継続的なヘルスチェックによるアクセスログ洪水を抑止する。
# （ログが肥大化すると BlueOS の VIEW LOGS が全件取得でタイムアウトするため）
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "9999", "--no-access-log"]