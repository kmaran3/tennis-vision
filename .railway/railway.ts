import { defineRailway, github, project, service, volume } from "railway/iac";
// This repository manages only its own resources in the environment. Other
// repositories export their own partial name.
// See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
export const partial = "tennis-vision";
export default defineRailway(() => {
  const quota = volume("tennis-vision-volume", {
    sizeMB: 5000, region: "us-west2", allowOnlineResize: true,
    alerts: { usage: { "80": {}, "95": {}, "100": {} } },
  });
  const tennisVision = service("tennis-vision", {
    source: github("kmaran3/tennis-vision", { branch: "main", checkSuites: false }),
    build: {
      buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile",
      watchPatterns: ["/baseline/**", "/frontend/**", "/Dockerfile", "/pyproject.toml", "/uv.lock", "/deployment/**", "/scripts/fetch_serving.py"],
    },
    healthcheck: "/health/ready",
    healthcheckTimeout: 120,
    replicas: { "us-west2": 1 },
    volumeMounts: { "/app/state": quota },
    deploy: {
      sleepApplication: true,
      restartPolicyType: "ON_FAILURE", restartPolicyMaxRetries: 3,
      limitOverride: { containers: { cpu: 0.5, memoryBytes: 536870912 } },
    },
  });

  return project("wonderful-truth", {
    variables: { managed: false },
    resources: [tennisVision, quota],
  });
});
