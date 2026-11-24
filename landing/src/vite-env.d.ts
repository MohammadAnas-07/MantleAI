/// <reference types="vite/client" />

declare module "virtual:screenshots" {
  const shots: { src: string; alt: string; width: number; height: number }[];
  export default shots;
}
