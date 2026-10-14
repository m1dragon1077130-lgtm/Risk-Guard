export async function onRequest(context) {
  const { request } = context;
  
  const cookies = request.headers.get('Cookie') || '';
  const sessionMatch = cookies.match(/session=([^;]+)/);
  
  if (!sessionMatch) {
    return new Response(JSON.stringify({ logged_in: false }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  
  try {
    const sessionData = JSON.parse(atob(sessionMatch[1]));
    
    return new Response(JSON.stringify({
      logged_in: true,
      user: {
        github_id: sessionData.github_id,
        username: sessionData.username,
        name: sessionData.name,
        avatar: sessionData.avatar,
      },
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (err) {
    return new Response(JSON.stringify({ logged_in: false }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
