// Written by `terraform apply` (see infra/terraform/web.tf), or by hand for
// local development. None of these are secrets.
window.MF_CONFIG = {
  apiBase: "https://send.ohteapea.com",
  region: "us-east-1",
  cognitoDomain: "https://REPLACE.auth.us-east-1.amazoncognito.com",
  clientId: "REPLACE",
  redirectUri: "https://app.ohteapea.com/",
};
