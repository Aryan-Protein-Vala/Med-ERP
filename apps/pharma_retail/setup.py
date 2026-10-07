from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="pharma_retail",
    version="0.0.1",
    description="Pharmacy Retail Management Application for Frappe and ERPNext",
    author="Aryan Sharma",
    author_email="admin@pharmacy.local",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
