export default function AuthLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <div className="h-screen h-[100dvh] w-full overflow-hidden">
            {children}
        </div>
    );
}
