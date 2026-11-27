#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const {Errors, GitHub, Manifest, VERSION} = require('release-please');
const {BranchName} = require('release-please/build/src/util/branch-name');
const {BaseStrategy} = require('release-please/build/src/strategies/base');

if (VERSION !== '17.6.0') {
  throw new Error(`release-please version mismatch: ${VERSION}`);
}

function writeOutput(value) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

function branchContract(components) {
  return components.map(component => {
    const branch = BranchName.ofComponentTargetBranch(component, 'main').toString();
    const parsed = BranchName.parse(branch);
    return {
      component,
      branch,
      parsedComponent: parsed && parsed.getComponent(),
      targetBranch: parsed && parsed.getTargetBranch(),
    };
  });
}

async function manifestContract(scenario) {
  const root = path.resolve(scenario.root);
  const lookups = [];
  const history = [];
  const candidateCommits = {};
  const buildReleasePullRequest = BaseStrategy.prototype.buildReleasePullRequest;
  BaseStrategy.prototype.buildReleasePullRequest = async function (commits, ...args) {
    candidateCommits[this.path] = commits.map(commit => commit.sha);
    return buildReleasePullRequest.call(this, commits, ...args);
  };
  const logger = {
    debug(message) {
      const match = /^looking for tagName: (.+)$/.exec(String(message));
      if (match) lookups.push(match[1]);
    },
    info() {},
    warn() {},
    error() {},
    trace() {},
  };
  const forbidden = () => {
    throw new Error('network and mutation APIs are forbidden in the local contract harness');
  };
  const octokit = new Proxy({}, {get: forbidden});
  const github = await GitHub.create({
    owner: 'local',
    repo: 'contract',
    defaultBranch: 'main',
    logger,
    octokitAPIs: {octokit, request: forbidden, graphql: forbidden},
  });
  github.getFileContentsOnBranch = async file => {
    let data;
    try {
      data = fs.readFileSync(path.join(root, file));
    } catch (error) {
      if (error && error.code === 'ENOENT') throw new Errors.FileNotFoundError(file);
      throw error;
    }
    return {
      content: data.toString('base64'),
      parsedContent: data.toString('utf8'),
      sha: 'f'.repeat(40),
      mode: '100644',
    };
  };
  github.releaseIterator = async function* () {
    for (const release of scenario.releases || []) yield release;
  };
  github.tagIterator = async function* () {
    for (const tag of scenario.tags || []) yield tag;
  };
  github.mergeCommitIterator = async function* () {
    for (const commit of scenario.commits || []) {
      history.push(commit.sha);
      yield commit;
    }
  };
  // buildPullRequests/buildChangeSet are the substantive release-pr --dry-run operations.
  const manifest = await Manifest.fromManifest(
    github,
    'main',
    'release-please-config.json',
    '.release-please-manifest.json',
    {logger}
  );
  const pullRequests = await manifest.buildPullRequests();
  const changes = {};
  for (const pullRequest of pullRequests) {
    const changeSet = await github.buildChangeSet(pullRequest.updates, 'main');
    for (const [file, change] of changeSet.entries()) {
      changes[file] = {
        content: change.content,
        originalContent: change.originalContent,
      };
    }
  }
  return {
    version: VERSION,
    lookups,
    history,
    candidateCommits,
    pullRequests: pullRequests.map(pullRequest => ({
      title: pullRequest.title.toString(),
      body: pullRequest.body.toString(),
      updates: pullRequest.updates.map(update => update.path),
    })),
    changes,
  };
}

async function main() {
  const scenario = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  if (scenario.branches) {
    writeOutput({version: VERSION, branches: branchContract(scenario.branches)});
    return;
  }
  writeOutput(await manifestContract(scenario));
}

main().catch(error => {
  process.stderr.write(`${error && error.message ? error.message : error}\n`);
  process.exitCode = 1;
});
