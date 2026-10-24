---
title: Pod stuck in ImagePullBackOff
tags: [kubernetes, imagepull, demo-app]
---

# Pod stuck in ImagePullBackOff / ErrImagePull

**What it means.** The node cannot download the container image. The pod
never starts. Nothing is wrong with the code that is already running
elsewhere; the new pod simply has no image.

**Causes, most common first.**
1. The image tag does not exist (typo, or a tag that was never built). The
   describe output says `manifest unknown` or `not found`.
2. The registry is private and the namespace has no pull secret: `unauthorized`.
3. The registry is unreachable from the node: `dial tcp ... i/o timeout`.

**How to confirm.**
- `kubectl describe pod <pod> -n <ns>`: look at `Events` for the exact
  reason and at `Image:` for the full reference.
- Compare the tag with what exists: the GitOps file
  `gitops/apps/<app>/deployment.yaml` holds the desired tag; the build
  workflow writes `sha-<7 chars>` tags and `main`.

**Fix.** Point the Deployment in git at a tag that exists. For the demo
app, the last known-good tag is the `sha-` tag written by the build
workflow (see `git log` on `gitops/apps/demo-app/deployment.yaml`), or
`main`. Change only the `image:` line. Never patch the live Deployment:
ArgoCD would revert it, and the fix must be in git.
