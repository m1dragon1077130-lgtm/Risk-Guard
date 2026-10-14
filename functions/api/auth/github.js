export async function onRequest(context) {
  const { env, request } = context;
  
  const clientId = env.GITHUB_CLIENT_ID;
  
  if (!clientId) {
    return new Response('Server error: GITHUB_CLIENT_ID not set', { status: 500 });
  }
  
  const origin = new URL(request.url).origin;
  const redirectUri = `${origin}/api/callback/github`;
  
  const state = crypto.randomUUID();
  
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    scope: 'repo workflow user:email',
    state: state,
  });
  
  const githubUrl = `https://github.com/login/oauth/authorize?${params}`;
  
  return new Response(null, {
    status: 302,
    headers: {
      'Location': githubUrl,
      'Set-Cookie': `oauth_state=${state}; HttpOnly; Secure; SameSite=Lax; Max-Age=600; Path=/`,
    },
  });
}
