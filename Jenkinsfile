// Jenkins 声明式流水线
//
// 流程：安装依赖 → 代码检查 → 单元测试 → 迁移校验（真实 MySQL）
//       → 构建镜像 → 推送镜像 → 部署测试环境 → （人工确认）部署生产环境
//
// Jenkins 节点要求：git、python3.12、docker（含 compose v2）、curl、ssh
// 凭据要求：
//   docker-registry-creds : Username with password（镜像仓库账号）
//   deploy-ssh-key        : SSH Username with private key（部署机免密登录）
//
// 参数 DEPLOY_ENV 控制本次发布范围：
//   staging    部署到测试环境（默认）
//   none       只跑 CI，不部署
//   production 先部署测试环境，人工确认后部署生产

// 普通 Pipeline 任务没有 BRANCH_NAME，退回到 GIT_BRANCH（形如 origin/main）
def currentBranch() {
    return (env.BRANCH_NAME ?: env.GIT_BRANCH ?: 'main')
        .replaceFirst('^origin/', '')
        .replaceAll('/', '-')
}

pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timeout(time: 90, unit: 'MINUTES')
    }

    parameters {
        choice(name: 'DEPLOY_ENV',
               choices: ['staging', 'none', 'production'],
               description: '本次发布到哪：staging 测试环境（默认），none 只做 CI，production 含生产（需人工确认）')
        string(name: 'REGISTRY', defaultValue: 'registry.example.com', description: '镜像仓库地址，不含协议')
        string(name: 'IMAGE_NAME', defaultValue: 'lxl-low-code-platform-backend', description: '镜像名')
        string(name: 'STAGING_HOST', defaultValue: 'staging.example.com', description: '测试服务器地址')
        string(name: 'PROD_HOST', defaultValue: 'prod.example.com', description: '生产服务器地址')
        string(name: 'DOCKER_CREDS_ID', defaultValue: 'docker-registry-creds', description: '镜像仓库凭据 ID')
        string(name: 'SSH_CREDS_ID', defaultValue: 'deploy-ssh-key', description: '服务器 SSH 凭据 ID')
    }

    environment {
        // BUILD_TAG 里可能带空格等 docker 不接受的字符，统一替换
        MYSQL_CI_NAME    = "mysql-ci-${env.BUILD_TAG.replaceAll('[^A-Za-z0-9_.-]', '_')}"
        MYSQL_CI_ROOT_PW = 'ciroot'
        MYSQL_CI_DB      = 'lxl_ci'
        IMAGE_REPO       = "${params.REGISTRY}/${params.IMAGE_NAME}"
        IMAGE_TAG        = "${currentBranch()}-${env.BUILD_NUMBER}"
        FULL_IMAGE       = "${params.REGISTRY}/${params.IMAGE_NAME}:${currentBranch()}-${env.BUILD_NUMBER}"
    }

    stages {

        stage('安装依赖') {
            steps {
                sh '''
                    set -e
                    python3 -m venv .venv
                    .venv/bin/pip install --quiet --upgrade pip
                    .venv/bin/pip install --quiet -r requirements.txt -r requirements-dev.txt
                '''
            }
        }

        stage('代码检查') {
            steps {
                sh '.venv/bin/ruff check app migrations'
            }
        }

        stage('单元测试') {
            steps {
                // 测试用内存 SQLite，不依赖外部数据库
                sh '.venv/bin/pytest -q'
            }
        }

        stage('迁移校验（真实 MySQL）') {
            steps {
                sh '''
                    set -e

                    docker rm -f "$MYSQL_CI_NAME" >/dev/null 2>&1 || true
                    docker run -d --name "$MYSQL_CI_NAME" \
                        -e MYSQL_ROOT_PASSWORD="$MYSQL_CI_ROOT_PW" \
                        -e MYSQL_DATABASE="$MYSQL_CI_DB" \
                        -p 127.0.0.1::3306 \
                        mysql:8.4

                    echo "等待 MySQL 就绪..."
                    READY=0
                    for i in $(seq 1 60); do
                        if docker exec "$MYSQL_CI_NAME" \
                            mysqladmin ping -h127.0.0.1 -uroot -p"$MYSQL_CI_ROOT_PW" --silent >/dev/null 2>&1; then
                            READY=1; break
                        fi
                        sleep 2
                    done
                    if [ "$READY" -ne 1 ]; then
                        echo "MySQL 启动超时"
                        docker logs --tail=50 "$MYSQL_CI_NAME" || true
                        exit 1
                    fi

                    PORT=$(docker port "$MYSQL_CI_NAME" 3306/tcp | head -n1 | sed 's/.*://')
                    echo "MySQL 端口: $PORT"

                    export DB_TYPE=mysql
                    export MYSQL_HOST=127.0.0.1
                    export MYSQL_PORT="$PORT"
                    export MYSQL_USER=root
                    export MYSQL_PASSWORD="$MYSQL_CI_ROOT_PW"
                    export MYSQL_DB="$MYSQL_CI_DB"

                    # 1) 从零建库，验证全部迁移脚本可重放
                    .venv/bin/alembic upgrade head

                    # 2) 模型改了却没生成迁移时，这一步会失败
                    .venv/bin/alembic check

                    .venv/bin/alembic current
                '''
            }
        }

        stage('构建镜像') {
            steps {
                sh '''
                    set -e
                    docker build --pull -t "$FULL_IMAGE" .
                    docker image inspect "$FULL_IMAGE" --format '镜像: {{.RepoTags}} 大小: {{.Size}}'
                '''
            }
        }

        stage('推送镜像') {
            when { expression { currentBranch() == 'main' } }
            steps {
                withCredentials([usernamePassword(
                        credentialsId: params.DOCKER_CREDS_ID,
                        usernameVariable: 'REG_USER',
                        passwordVariable: 'REG_PASS')]) {
                    sh '''
                        set -e
                        echo "$REG_PASS" | docker login "$REGISTRY" -u "$REG_USER" --password-stdin
                        docker push "$FULL_IMAGE"
                    '''
                }
            }
        }

        stage('部署到测试环境') {
            when {
                allOf {
                    expression { currentBranch() == 'main' }
                    expression { params.DEPLOY_ENV != 'none' }
                }
            }
            steps {
                withCredentials([sshUserPrivateKey(
                        credentialsId: params.SSH_CREDS_ID,
                        keyFileVariable: 'SSH_KEY',
                        usernameVariable: 'SSH_USER')]) {
                    sh """
                        set -e
                        ssh -i "\$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 \\
                            "\$SSH_USER@${params.STAGING_HOST}" \\
                            "cd /srv/lxl-staging && git pull --ff-only && IMAGE=${FULL_IMAGE} ./deploy/deploy.sh staging ${FULL_IMAGE}"
                    """
                }
            }
        }

        stage('部署到生产环境') {
            when {
                allOf {
                    expression { currentBranch() == 'main' }
                    expression { params.DEPLOY_ENV == 'production' }
                }
            }
            // 人工确认闸门：没人确认就一直等（受全局 timeout 限制，超时中止且不会部署）
            input {
                message "即将把 ${FULL_IMAGE} 发布到生产环境，确认继续？"
                ok '确认发布'
            }
            steps {
                withCredentials([sshUserPrivateKey(
                        credentialsId: params.SSH_CREDS_ID,
                        keyFileVariable: 'SSH_KEY',
                        usernameVariable: 'SSH_USER')]) {
                    sh """
                        set -e
                        ssh -i "\$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 \\
                            "\$SSH_USER@${params.PROD_HOST}" \\
                            "cd /srv/lxl-production && git pull --ff-only && IMAGE=${FULL_IMAGE} ./deploy/deploy.sh production ${FULL_IMAGE}"
                    """
                }
            }
        }
    }

    post {
        always {
            sh "docker rm -f \"$MYSQL_CI_NAME\" >/dev/null 2>&1 || true"
        }
        failure {
            echo '流水线失败：请查看对应 stage 的日志。生产环境如需回滚，从服务器 backups/ 目录取最近的备份。'
        }
    }
}
