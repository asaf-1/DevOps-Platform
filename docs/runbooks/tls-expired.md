---
title: Ingress serves an expired TLS certificate
tags: [kubernetes, tls, ingress, demo-app]
---

# Ingress serves an expired TLS certificate

**What it means.** The Ingress names a `kubernetes.io/tls` Secret whose
certificate is past its `notAfter` date. The app itself is healthy; the
browser refuses the connection (`NET::ERR_CERT_DATE_INVALID`) and the
ingress controller logs `certificate in secret <ns>/<name> expired`.

**How to confirm.**
- `kubectl describe ingress <name> -n <ns>`: the `TLS:` block names the
  Secret in use; the `Events` say which certificate expired and when.
- `kubectl get secret -n <ns>`: list the TLS secrets that exist. A newer
  one (small `AGE`) next to the old one is the renewed certificate.
- `kubectl describe secret <name> -n <ns>`: `tls.crt` shows `notAfter`;
  the one in the future is valid.

**Fix, in git.** The Ingress is `gitops/apps/<app>/ingress.yaml`. Change
only the `secretName:` line under `tls:` to the Secret whose certificate
is valid. Do not create, copy or edit Secrets, and do not change the
`hosts` or the rules. If no valid Secret exists, say so: renewing a
certificate is a cert-manager or human task, not a GitOps change.
