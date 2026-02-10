#!/usr/bin/env node
/**
 * 生成 20,000 个扩展 Skills 到 SCC Skill 库
 * 
 * 包含：
 * 1. 更多编程语言和框架
 * 2. 更多领域特定技能
 * 3. 更多工具和实践
 * 4. 动态加载和自迭代相关技能
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');
const SKILLS_DIR = path.join(REPO_ROOT, 'L4_prompt_layer', 'skills');
const REGISTRY_FILE = path.join(SKILLS_DIR, 'registry.json');
const MATRIX_FILE = path.join(REPO_ROOT, 'L4_prompt_layer', 'roles', 'role_skill_matrix.json');

// 扩展的 Skill 类别 - 20,000个skills的分类体系
const EXTENDED_SKILL_CATEGORIES = {
  // 编程语言 - 扩展
  'ext.programming': {
    description: '扩展编程语言技能',
    skills: [
      // 主流语言变体
      'javascript.es6', 'javascript.typescript', 'javascript.nodejs', 'javascript.deno', 'javascript.bun',
      'python.data_science', 'python.web', 'python.automation', 'python.ml', 'python.scripting',
      'java.spring', 'java.android', 'java.microservices', 'java.reactive', 'java.graalvm',
      'csharp.dotnet', 'csharp.unity', 'csharp.xamarin', 'csharp.blazor', 'csharp.maui',
      'go.microservices', 'go.cloud_native', 'go.cli', 'go.web', 'go.systems',
      'rust.systems', 'rust.web', 'rust.embedded', 'rust.blockchain', 'rust.gamedev',
      'cpp.systems', 'cpp.gamedev', 'cpp.embedded', 'cpp.finance', 'cpp.hpc',
      
      // 函数式语言
      'haskell.pure', 'haskell.web', 'elm.frontend', 'purescript.functional', 'clojure.jvm',
      'clojurescript.frontend', 'erlang.concurrent', 'elixir.phoenix', 'fsharp.dotnet', 'ocaml.systems',
      
      // 脚本语言
      'ruby.rails', 'ruby.sinatra', 'ruby.automation', 'ruby.devops', 'ruby.testing',
      'php.laravel', 'php.symfony', 'php.wordpress', 'php.magento', 'php.cms',
      'perl.scripting', 'perl.web', 'perl.bioinformatics', 'perl.systems', 'perl.legacy',
      'lua.gamedev', 'lua.embedded', 'lua.neovim', 'lua.scripting', 'lua.web',
      
      // JVM语言
      'kotlin.android', 'kotlin.server', 'kotlin.multiplatform', 'kotlin.scripting', 'kotlin.data',
      'scala.bigdata', 'scala.akka', 'scala.web', 'scala.functional', 'scala.spark',
      'groovy.gradle', 'groovy.scripting', 'groovy.testing', 'groovy.web', 'groovy.devops',
      
      // 新兴语言
      'zig.systems', 'zig.embedded', 'zig.web', 'vlang.systems', 'vlang.web',
      'crystal.web', 'crystal.cli', 'crystal.systems', 'nim.systems', 'nim.web',
      'dart.flutter', 'dart.web', 'dart.server', 'dart.cli', 'dart.embedded',
      
      // 特定领域语言
      'r.data_science', 'r.statistics', 'r.bioinformatics', 'r.finance', 'r.visualization',
      'matlab.engineering', 'matlab.signal', 'matlab.control', 'matlab.simulation', 'matlab.finance',
      'julia.scientific', 'julia.ml', 'julia.data', 'julia.parallel', 'julia.optimization',
      
      // Web专用
      'webassembly.systems', 'webassembly.web', 'webassembly.gamedev', 'webassembly.edge', 'webassembly.portable',
      
      // 数据库语言
      'sql.postgresql', 'sql.mysql', 'sql.sqlite', 'sql.oracle', 'sql.mssql',
      'nosql.mongodb', 'nosql.redis', 'nosql.cassandra', 'nosql.dynamodb', 'nosql.firebase',
      
      // 标记和样式
      'html.semantic', 'html.email', 'html.accessibility', 'css.modern', 'css.animations',
      'scss.advanced', 'less.styles', 'sass.architecture', 'postcss.processing', 'tailwind.custom',
      
      // 配置和模板
      'yaml.config', 'yaml.cicd', 'yaml.cloud', 'json.schema', 'json.api',
      'toml.config', 'toml.rust', 'xml.data', 'xml.soap', 'xml.config',
      
      // 其他
      'bash.scripting', 'bash.automation', 'bash.devops', 'powershell.admin', 'powershell.automation',
      'awk.text', 'sed.text', 'regex.patterns', 'regex.validation', 'regex.parsing',
    ]
  },

  // 前端框架和库 - 扩展
  'ext.frontend': {
    description: '扩展前端开发技能',
    skills: [
      // React生态
      'react.hooks', 'react.context', 'react.redux', 'react.mobx', 'react.query',
      'react.nextjs', 'react.remix', 'react.gatsby', 'react.react_native', 'react.electron',
      'react.testing', 'react.performance', 'react.accessibility', 'react.ssr', 'react.pwa',
      
      // Vue生态
      'vue.composition', 'vue.options', 'vue.pinia', 'vue.vuex', 'vue.nuxt',
      'vue.testing', 'vue.performance', 'vue.ssr', 'vue.pwa', 'vue.mobile',
      
      // Angular生态
      'angular.components', 'angular.services', 'angular.rxjs', 'angular.ngrx', 'angular.material',
      'angular.testing', 'angular.performance', 'angular.ssr', 'angular.pwa', 'angular.enterprise',
      
      // Svelte生态
      'svelte.sveltekit', 'svelte.stores', 'svelte.transitions', 'svelte.testing', 'svelte.performance',
      
      // 其他框架
      'solidjs.reactive', 'qwik.resumable', 'alpine.lightweight', 'htmx.interactive', 'petite_vue',
      
      // UI组件库
      'mui.material', 'antd.enterprise', 'chakra.modern', 'tailwindui.utility', 'shadcn.custom',
      'bootstrap.classic', 'bulma.modern', 'foundation.responsive', 'semantic.ui', 'primer.github',
      
      // 样式解决方案
      'styled_components.cssinjs', 'emotion.react', 'linaria.zero', 'vanilla_extract.type', 'stitches.cssinjs',
      
      // 状态管理
      'zustand.simple', 'jotai.atomic', 'recoil.react', 'valtio.proxy', 'xstate.state_machine',
      
      // 数据获取
      'tanstack_query.data', 'swr.react', 'urql.graphql', 'apollo.client', 'relay.modern',
      
      // 表单处理
      'react_hook_form.performant', 'formik.forms', 'final_form', 'vee_validate.vue', 'vuelidate.validation',
      
      // 动画
      'framer_motion.react', 'gsap.professional', 'threejs.3d', 'd3.data_viz', 'lottie.animations',
      
      // 图表
      'chartjs.simple', 'recharts.react', 'victory.react', 'plotly.interactive', 'echarts.baidu',
      
      // 地图
      'leaflet.open', 'mapbox.gl', 'google_maps', 'openlayers', 'deck.gl',
      
      // 编辑器
      'monaco.editor', 'codemirror', 'quill.rich', 'tiptap.headless', 'slate.customizable',
      
      // 表格
      'ag_grid.enterprise', 'react_table.headless', 'tanstack_table.modern', 'handsontable.excel', 'data_tables.jquery',
      
      // 日期时间
      'date_fns.modern', 'dayjs.lightweight', 'luxon.powerful', 'moment.legacy', 'temporal.future',
      
      // 工具库
      'lodash.utilities', 'ramda.functional', 'underscore.classic', 'datejs.dates', 'numeral.numbers',
    ]
  },

  // 后端框架 - 扩展
  'ext.backend': {
    description: '扩展后端开发技能',
    skills: [
      // Node.js框架
      'express.classic', 'fastify.performant', 'koa.modern', 'nestjs.enterprise', 'hapi.structured',
      'sails.mvc', 'adonis.laravel', 'feathers.realtime', 'loopback.ibm', 'meteor.fullstack',
      
      // Python框架
      'django.fullstack', 'flask.micro', 'fastapi.modern', 'tornado.async', 'pyramid.flexible',
      'bottle.micro', 'falcon.performant', 'sanic.async', 'tornado.websocket', 'dash.data',
      
      // Go框架
      'gin.fast', 'echo.minimal', 'fiber.express', 'beego.full', 'buffalo.fullstack',
      'revel.mvc', 'martini.classic', 'iris.performant', 'gozero.microservices', 'kratos.bilibili',
      
      // Java框架
      'spring_boot.enterprise', 'spring_cloud.microservices', 'spring_security.auth', 'spring_data.data', 'spring_batch.batch',
      'quarkus.cloud', 'micronaut.modern', 'vertx.reactive', 'helidon.oracle', 'dropwizard.ops',
      
      // Rust框架
      'actix_web.fast', 'rocket.modern', 'axum.tokio', 'tide.http', 'warp.filters',
      
      // PHP框架
      'lararavel.elegant', 'symfony.robust', 'codeigniter.light', 'cakephp.convention', 'zend.enterprise',
      'slim.micro', 'lumen.laravel', 'yii.fast', 'phalcon.c', 'fuelphp.flexible',
      
      // Ruby框架
      'rails.convention', 'sinatra.micro', 'hanami.modern', 'grape.api', 'padrino.agile',
      
      // API开发
      'graphql.apollo', 'graphql.relay', 'rest.openapi', 'grpc.protobuf', 'websocket.socketio',
      'trpc.typesafe', 'jsonapi.standard', 'odata.microsoft', 'swagger.docs', 'postman.testing',
      
      // 认证授权
      'jwt.tokens', 'oauth2.flows', 'openid_connect.identity', 'saml.enterprise', 'ldap.directory',
      'auth0.saas', 'keycloak.open', 'casdoor.modern', 'casbin.policy', 'ory.modern',
      
      // 缓存
      'redis.caching', 'memcached.distributed', 'hazelcast.imdg', 'ehcache.java', 'caffeine.high_performance',
      
      // 消息队列
      'rabbitmq.amqp', 'kafka.distributed', 'activemq.classic', 'rocketmq.alibaba', 'nats.lightweight',
      'pulsar.apache', 'zeromq.socket', 'sqs.aws', 'pubsub.gcp', 'service_bus.azure',
      
      // 搜索引擎
      'elasticsearch.search', 'solr.apache', 'meilisearch.modern', 'algolia.hosted', 'typesense.open',
      
      // 任务调度
      'celery.python', 'sidekiq.ruby', 'bull.node', 'hangfire.dotnet', 'quartz.java',
      'agenda.node', 'bee_queue.redis', 'kue.node', 'delayed_job.ruby', 'resque.redis',
    ]
  },

  // 数据库 - 扩展
  'ext.database': {
    description: '扩展数据库技能',
    skills: [
      // 关系型数据库
      'postgresql.advanced', 'mysql.popular', 'sqlite.embedded', 'oracle.enterprise', 'mssql.microsoft',
      'mariadb.mysql', 'cockroachdb.distributed', 'citus.distributed', 'timescaledb.time', 'planetscale.serverless',
      
      // NoSQL文档
      'mongodb.document', 'couchdb.sync', 'firestore.google', 'dynamodb.aws', 'cosmosdb.azure',
      'couchbase.distributed', 'ravendb.net', 'rethinkdb.realtime', 'fauna.serverless', 'supabase.postgres',
      
      // NoSQL键值
      'redis.versatile', 'memcached.simple', 'etcd.distributed', 'consul.service', 'zookeeper.coordination',
      'keydb.redis', 'dragonfly.modern', 'rocksdb.embedded', 'leveldb.google', 'bolt.db',
      
      // NoSQL宽列
      'cassandra.distributed', 'hbase.hadoop', 'scylladb.cassandra', 'bigtable.google', 'dynamodb.wide',
      
      // NoSQL图
      'neo4j.graph', 'amazon_neptune.aws', 'arangodb.multi_model', 'orientdb.multi_model', 'janusgraph.distributed',
      'dgraph.native', 'tigergraph.enterprise', 'nebula.chinese', 'memgraph.realtime', 'terminusdb.version',
      
      // 时序数据库
      'influxdb.time', 'timescaledb.postgres', 'prometheus.monitoring', 'tdengine.iot', 'questdb.fast',
      'clickhouse.analytics', 'druid.apache', 'pinot.linkedin', 'iotdb.apache', 'btrdb.berkeley',
      
      // 向量数据库
      'pinecone.hosted', 'weaviate.open', 'milvus.zilliz', 'qdrant.rust', 'chromadb.embeddings',
      'pgvector.postgres', 'redisearch.redis', 'elasticsearch.vectors', 'faiss.facebook', 'annoy.spotify',
      
      // 搜索引擎数据库
      'elasticsearch.full', 'opensearch.aws', 'meilisearch.light', 'algolia.hosted', 'typesense.open',
      'sonic.fast', 'quickwit.cloud', 'tantivy.rust', 'bleve.go', 'manticore.search',
      
      // 区块链数据库
      'ipfs.distributed', 'arweave.permanent', 'filecoin.storage', 'bigchaindb.blockchain', 'fluree.graph',
      
      // ORM和查询构建
      'prisma.modern', 'typeorm.typescript', 'sequelize.node', 'mongoose.mongodb', 'sqlalchemy.python',
      'hibernate.java', 'entity_framework.dotnet', 'gorm.go', 'diesel.rust', 'diesel.orm',
      'jooq.typesafe', 'mybatis.java', 'dapper.dotnet', 'peewee.python', 'tortoise.async',
      
      // 数据库工具
      'flyway.migration', 'liquibase.java', 'dbmate.simple', 'golang_migrate.go', 'alembic.python',
      'prisma_migrate.modern', 'typeorm_migrations.typescript', 'knex.query', 'drizzle.modern', 'kysely.typesafe',
    ]
  },

  // DevOps和云 - 扩展
  'ext.devops': {
    description: '扩展DevOps和云技能',
    skills: [
      // 容器化
      'docker.containerization', 'kubernetes.orchestration', 'containerd.runtime', 'crio.lightweight', 'podman.daemonless',
      'docker_compose.local', 'helm.kubernetes', 'kustomize.kubernetes', 'skaffold.development', 'tilt.local',
      
      // CI/CD平台
      'github_actions.modern', 'gitlab_ci.gitlab', 'jenkins.classic', 'circleci.cloud', 'travis_ci.legacy',
      'azure_devops.microsoft', 'aws_codepipeline.aws', 'google_cloud_build.gcp', 'drone.lightweight', 'argo.workflows',
      'tekton.kubernetes', 'spinnaker.netflix', 'flux.gitops', 'argo_cd.gitops', 'flagger.progressive',
      
      // 基础设施即代码
      'terraform.hashicorp', 'pulumi.modern', 'aws_cloudformation.aws', 'azure_resource_manager.azure', 'google_deployment_manager.gcp',
      'ansible.automation', 'puppet.enterprise', 'chef.automation', 'saltstack.automation', 'vagrant.local',
      
      // 云平台
      'aws.amazon', 'azure.microsoft', 'gcp.google', 'alicloud.alibaba', 'tencent_cloud.tencent',
      'oracle_cloud.oracle', 'ibm_cloud.ibm', 'digital_ocean.simple', 'linode.akamai', 'vultr.cloud',
      'heroku.platform', 'vercel.edge', 'netlify.jamstack', 'railway.modern', 'render.platform',
      'fly.io.edge', 'deno_deploy.edge', 'cloudflare.workers', 'fastly.edge', 'stackpath.edge',
      
      // 监控和可观测性
      'prometheus.metrics', 'grafana.visualization', 'datadog.saas', 'new_relic.observability', 'dynatrace.enterprise',
      'appdynamics.cisco', 'splunk.logs', 'elk_stack.open', 'loki.grafana', 'jaeger.tracing',
      'zipkin.tracing', 'opentelemetry.standard', 'sentry.errors', 'bugsnag.errors', 'rollbar.errors',
      'pagerduty.incident', 'opsgenie.incident', 'victorops.incident', 'xmatters.notification', 'statuspage.atlassian',
      
      // 日志管理
      'elk_stack.elastic', 'fluentd.collection', 'logstash.processing', 'graylog.open', 'loki.grafana',
      'splunk.enterprise', 'sumo_logic.saas', 'papertrail.hosted', 'logdna.mezmo', 'loggly.solarwinds',
      
      // 服务网格
      'istio.service_mesh', 'linkerd.lightweight', 'consul_connect.hashicorp', 'traefik_mesh.traefik', 'kuma.kong',
      
      // GitOps
      'argocd.kubernetes', 'fluxcd.gitops', 'flagger.progressive', 'keptn.lifecycles', 'werf.russian',
      
      // 安全和合规
      'vault.hashicorp', 'cert_manager.kubernetes', 'lets_encrypt.free', 'acme.protocol', 'snyk.security',
      'sonarqube.code_quality', 'checkov.iac', 'tfsec.terraform', 'trivy.container', 'grype.anchore