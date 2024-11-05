// TEST

struct MyBase {
    virtual int Foo() { return 0; }
};

struct Child1 final : public MyBase {
    int Foo() override { return 1; }
};
struct Child2 final : public MyBase {
    int Foo() override { return 2; }
};

__attribute__((noinline))
int DoFoo(MyBase *inst) {
    asm volatile ("":::"memory");
    return inst->Foo();
}

int main (int argc, char **argv) {
    MyBase *inst = nullptr;
    if (argc == 1)
        inst = new MyBase();
    else if (argc == 2)
        inst = new Child1();
    else
        inst = new Child2();
    return DoFoo(inst);
}
