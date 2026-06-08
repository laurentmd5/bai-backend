// Déploiement sur VM Ubuntu - Dossier /home/devops/barrow-ai-poc

pipeline {
    agent any
    
    environment {
        DOCKER_IMAGE_NAME = 'barrow'
        DOCKER_IMAGE_TAG = "${BUILD_NUMBER}"
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
        stage('Clone') {
            steps {
                echo 'Clonage du depot GitHub...'
                checkout scm
                script {
                    currentBuild.displayName = "#${BUILD_NUMBER} - ${GIT_COMMIT.take(8)}"
                }
            }
        }
        
        // =====================================================================
        // STAGE 2 : BUILD
        // =====================================================================
        stage('Build') {
            steps {
                script {
                    echo "Construction : ${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG}"
                    docker.build("${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG}", "-f Dockerfile .")
                }
            }
        }
        
        // =====================================================================
        // STAGE 3 : PREPARER
        // =====================================================================
        stage('Preparer') {
            steps {
                script {
                    sh """
                        mkdir -p ${DEPLOY_PATH}/logs
                        mkdir -p ${DEPLOY_PATH}/scripts
                        mkdir -p ${DEPLOY_PATH}/traefik

                        cp ${WORKSPACE}/${COMPOSE_FILE}              ${DEPLOY_PATH}/
                        cp ${WORKSPACE}/scripts/init_qdrant.py       ${DEPLOY_PATH}/scripts/
                        cp ${WORKSPACE}/scripts/create_admin.py      ${DEPLOY_PATH}/scripts/
                        cp ${WORKSPACE}/scripts/db_migrate.py        ${DEPLOY_PATH}/scripts/
                        cp ${WORKSPACE}/traefik/traefik.yml          ${DEPLOY_PATH}/traefik/
                        cp ${WORKSPACE}/traefik/config.yml           ${DEPLOY_PATH}/traefik/
                    """

                    def envExists = sh(
                        script: "test -f ${DEPLOY_PATH}/.env && echo yes || echo no",
                        returnStdout: true
                    ).trim()

                    if (envExists == 'no') {
                        echo 'ATTENTION : .env manquant - Creez-le sur la VM : nano /home/devops/barrow-ai-poc/.env'
                        sh "cp ${WORKSPACE}/.env.example ${DEPLOY_PATH}/.env"
                    } else {
                        echo '.env conserve'
                    }
                }
            }
        }

        // =====================================================================
        // STAGE 4 : REDEMARRER
        // =====================================================================
        stage('Redemarrer') {
            steps {
                sh """
                    cd ${DEPLOY_PATH}
                    docker compose -f ${COMPOSE_FILE} down --remove-orphans || true
                    docker compose -f ${COMPOSE_FILE} up -d --force-recreate
                """
                sleep(time: 20, unit: 'SECONDS')
            }
        }

        // =====================================================================
        // STAGE 5 : VERIFIER
        // =====================================================================
        stage('Verifier') {
            steps {
                script {
                    def ok = false
                    for (int i = 0; i < 20; i++) {
                        def status = sh(
                            script: "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health || echo 000",
                            returnStdout: true
                        ).trim()
                        if (status == '200') {
                            ok = true
                            echo "Service healthy (tentative ${i + 1})"
                            break
                        }
                        sleep(time: 3, unit: 'SECONDS')
                    }
                    if (!ok) error("Service non healthy apres 20 tentatives")
                }
            }
        }

        // =====================================================================
        // STAGE 6 : MIGRATION DB (hybrid create_all + alembic)
        //
        //   - Premier deploiement  : create_all() puis alembic stamp head
        //   - Deploiements suivants: alembic upgrade head (nouvelles migrations)
        //
        //   Le script scripts/db_migrate.py gere automatiquement les deux cas.
        //   Aucune condition fragile : tourne a chaque deploiement, est idempotent.
        // =====================================================================
        stage('Migration DB') {
            steps {
                script {
                    echo 'Application du schema de base de donnees (hybride create_all + Alembic)...'
                    sh """
                        cd ${DEPLOY_PATH}
                        docker compose -f ${COMPOSE_FILE} exec -T backend python scripts/db_migrate.py
                    """
                    echo 'Schema OK'
                }
            }
        }

        // =====================================================================
        // STAGE 7 : INIT DATA (admin + Qdrant) — uniquement si besoin
        //
        //   Cree l'administrateur initial si la table admin_users est vide.
        //   Initialise Qdrant (operation idempotente).
        // =====================================================================
        stage('Init Data') {
            steps {
                script {
                    // Compter les admins existants
                    def adminCount = sh(
                        script: """
                            cd ${DEPLOY_PATH}
                            docker compose -f ${COMPOSE_FILE} exec -T postgres \
                                psql -U barrowai -d barrowai_poc -tAq \
                                -c "SELECT COUNT(*) FROM admin_users;" 2>/dev/null || echo 0
                        """,
                        returnStdout: true
                    ).trim()

                    if (adminCount == '0') {
                        echo 'Aucun administrateur trouve — creation du compte initial...'
                        sh """
                            cd ${DEPLOY_PATH}
                            docker compose -f ${COMPOSE_FILE} exec -T backend \
                                python scripts/create_admin.py \
                                    --email admin@pace.gm \
                                    --name 'PACE Admin' \
                                    --role superadmin \
                                    --password Admin123!
                        """
                    } else {
                        echo "Administrateurs existants (${adminCount}) — creation ignoree"
                    }

                    // Toujours initialiser Qdrant (idempotent)
                    sh """
                        cd ${DEPLOY_PATH}
                        docker compose -f ${COMPOSE_FILE} exec -T backend \
                            python scripts/init_qdrant.py || true
                    """
                }
            }
        }

        // =====================================================================
        // STAGE 8 : NETTOYER
        // =====================================================================
        stage('Nettoyer') {
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
========================================
     DEPLOIEMENT REUSSI !
========================================
  API     : http://${ip}:8000/health
  Docs    : http://${ip}:8000/docs
  Admin   : admin@pace.gm / Admin123!
========================================"""
            }
        }
        failure {
            sh "cd ${DEPLOY_PATH} && docker compose -f ${COMPOSE_FILE} logs --tail 30 || true"
        }
    }
}