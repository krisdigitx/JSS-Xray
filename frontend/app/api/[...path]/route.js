const BACKEND = process.env.BACKEND_INTERNAL_URL || "http://jss-xray-backend:8000";

async function proxy(request, context) {
  const { path } = await context.params;
  const incoming = new URL(request.url);
  const target = new URL(`/api/${path.join("/")}${incoming.search}`, BACKEND);

  const init = {
    method: request.method,
    headers: {
      "accept": request.headers.get("accept") || "application/json",
      "content-type": request.headers.get("content-type") || "application/json",
    },
    cache: "no-store",
  };

  if (!["GET", "HEAD"].includes(request.method)) {
    init.body = await request.text();
  }

  const response = await fetch(target, init);
  const body = await response.arrayBuffer();

  return new Response(body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "application/json",
    },
  });
}

export async function GET(request, context) {
  return proxy(request, context);
}

export async function POST(request, context) {
  return proxy(request, context);
}
