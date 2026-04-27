// Déploiement sur VM Ubuntu - Dossier /home/devops/barrow-ai-poc

pipeline {
    agent any
    
    environment {
        DOCKER_IMAGE_NAME = 'barrowai_backend'
        DOCKER_IMAGE_TAG = "${BUILD_NUMBER}_${GIT_COMMIT.take(8)}"
        DEPLOY_PATH = '/home/devops/barrow-ai-poc'
        COMPOSE_FILE = 'docker-compose.dev.yml'
    }
    
    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }
    
    stages {
        
        // =====================================================================
        // STAGE 1 : CLONE
        // =====================================================================
        stage('📦 Clone') {
            steps {
                echo 'Clonage du dépôt GitHub...'
                checkout scm
                script {
                    currentBuild.displayName = "#${BUILD_NUMBER} - ${GIT_COMMIT.take(8)}"
                }
            }
        }
        
        // =====================================================================
        // STAGE 2 : BUILD
        // =====================================================================
        stage('🐳 Build') {
            steps {
                script {
                    docker.build(
                        "${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG}",
                        "-f Dockerfile ."
                    )
                    docker.image("${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG}").tag("${DOCKER_IMAGE_NAME}:latest")
                }
            }
        }
        
        // =====================================================================
        // STAGE 3 : PRÉPARER
        // =====================================================================
        stage('📁 Préparer') {
            steps {
                script {
                    sh """
                        mkdir -p ${DEPLOY_PATH}/logs
                        mkdir -p ${DEPLOY_PATH}/scripts
                        mkdir -p ${DEPLOY_PATH}/traefik
                        
                        cp ${WORKSPACE}/${COMPOSE_FILE} ${DEPLOY_PATH}/
                        cp ${WORKSPACE}/scripts/init_qdrant.py ${DEPLOY_PATH}/scripts/
                        cp ${WORKSPACE}/scripts/create_admin.py ${DEPLOY_PATH}/scripts/
                        cp ${WORKSPACE}/traefik/traefik.yml ${DEPLOY_PATH}/traefik/
                        cp ${WORKSPACE}/traefik/config.yml ${DEPLOY_PATH}/traefik/
                    """
                    
                    // .env : ne pas écraser
                    def envExists = sh(
                        script: "test -f ${DEPLOY_PATH}/.env && echo yes || echo no",
                        returnStdout: true
                    ).trim()
                    
                    if (envExists == 'no') {
                        echo '⚠️  .env manquant - Créez-le sur la VM : nano /home/devops/barrow-ai-poc/.env'
                        sh "cp ${WORKSPACE}/.env.example ${DEPLOY_PATH}/.env"
                    } else {
                        echo '✅ .env conservé'
                    }
                }
            }
        }
        
        // =====================================================================
        // STAGE 4 : REDÉMARRER
        // =====================================================================
        stage('⏸️ Redémarrer') {
            steps {
                sh """
                    cd ${DEPLOY_PATH}
                    docker compose -f ${COMPOSE_FILE} down --remove-orphans || true
                    docker compose -f ${COMPOSE_FILE} up -d --force-recreate
                """
                sleep(time: 15, unit: 'SECONDS')
            }
        }
        
        // =====================================================================
        // STAGE 5 : VÉRIFIER
        // =====================================================================
        stage('🏥 Vérifier') {
            steps {
                script {
                    def ok = false
                    for (int i = 0; i < 15; i++) {
                        def status = sh(script: "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health || echo 000", returnStdout: true).trim()
                        if (status == '200') { ok = true; echo "✅ Healthy (${i + 1})"; break }
                        sleep(time: 3, unit: 'SECONDS')
                    }
                    if (!ok) error("❌ Service non healthy")
                }
            }
        }
        
        // =====================================================================
        // STAGE 6 : INIT (premier déploiement)
        // =====================================================================
        stage('🆕 Init DB') {
            when {
                expression {
                    def r = sh(script: "cd ${DEPLOY_PATH} && docker compose -f ${COMPOSE_FILE} exec -T postgres psql -U barrowai -d barrowai_poc -t -c \"SELECT COUNT(*) FROM admin_users;\" 2>/dev/null || echo 0", returnStdout: true).trim()
                    return r == '0'
                }
            }
            steps {
                sh """
                    cd ${DEPLOY_PATH}
                    docker compose -f ${COMPOSE_FILE} exec -T backend alembic upgrade head || true
                    docker compose -f ${COMPOSE_FILE} exec -T backend python scripts/create_admin.py --email admin@pace.gm --name 'PACE Admin' --role superadmin --password Admin123! || true
                    docker compose -f ${COMPOSE_FILE} exec -T backend python scripts/init_qdrant.py || true
                """
            }
        }
        
        // =====================================================================
        // STAGE 7 : NETTOYER
        // =====================================================================
        stage('🧹 Nettoyer') {
            steps {
                sh 'docker image prune -f || true'
            }
        }
    }
    
    post {
        success {
            script {
                def ip = sh(script: "hostname -I | awk '{print \$1}'", returnStdout: true).trim()
                echo """
╔══════════════════════════════════════════════╗
║        🎉  DÉPLOIEMENT RÉUSSI              ║
╠══════════════════════════════════════════════╣
║  API     : http://${ip}:8000/health
║  Docs    : http://${ip}:8000/docs
║  Admin   : admin@pace.gm / Admin123!
╚══════════════════════════════════════════════╝"""
            }
        }
        failure {
            sh "cd ${DEPLOY_PATH} && docker compose -f ${COMPOSE_FILE} logs --tail 30 || true"
        }
    }
}
