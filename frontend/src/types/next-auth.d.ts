import "next-auth";

declare module "next-auth" {
  interface Session {
    accessToken: string;
    role: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    accessToken: string;
    role: string;
  }
}
